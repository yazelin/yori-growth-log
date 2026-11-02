"""Larch agent REST 的薄包裝，只用 stdlib。

認證用固定的 Bearer 金鑰（LARCH_AGENT_KEY）。不走 MCP（一次呼叫約 30 秒）。
寫入限流是整個帳號共用，連續十幾次就回 429，照 retry-after 等完再送。

這裡直接拒絕兩種請求：
- 發佈到市集（/publish）：只有 publish() 能走，而且只送 POST（更新上架），下架（DELETE）一律擋。
- PUT /projects/<id>：整包覆寫會靜默洗掉沒帶到的欄位。只有 replace_project 能走，
  而它只給「先讀整份、改一個欄位、原樣推回」用（專案簡介沒有別的寫法）。
"""
import base64
import json
import mimetypes
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://larch.ink/api/agent"
MAX_TRIES = 5


class LarchError(Exception):
    def __init__(self, status, body):
        super().__init__(f"Larch HTTP {status}: {str(body)[:300]}")
        self.status = status
        self.body = body


class Larch:
    def __init__(self, key, base=BASE, sleep=time.sleep, opener=urllib.request.urlopen):
        self.key = key
        self.base = base.rstrip("/")
        self.sleep = sleep
        self.opener = opener

    def request(self, method, path, body=None, headers=None, _whole_project=False, _publish=False):
        # 只認結尾的 /publish：/published（列出已上架作品）是唯讀的，不能一起擋
        if re.search(r"/publish/?$", path) and not (_publish and method == "POST"):
            raise LarchError(0, f"拒絕呼叫發佈端點：{method} {path}")
        if method == "PUT" and re.fullmatch(r"/projects/[^/]+/?", path) and not _whole_project:
            raise LarchError(0, f"拒絕整包覆寫專案：{path}")
        h = {"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        data = None
        if body is not None:
            h["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode()
        h.update(headers or {})
        for attempt in range(1, MAX_TRIES + 1):
            req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
            try:
                with self.opener(req, timeout=180) as r:
                    raw = r.read()
                    out = json.loads(raw) if raw else {}
                    etag = r.headers.get("ETag") if r.headers else None
                    if etag and isinstance(out, dict):
                        out["_etag"] = etag
                    return out
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", "replace")
                # 429 一律等完重送；502/503 只有冪等的 GET/PUT 才重送，
                # POST 收到 502 時伺服器可能已經寫進去了，重送會多一筆。
                retry = e.code == 429 or (e.code in (502, 503) and method in ("GET", "PUT"))
                if not retry or attempt == MAX_TRIES:
                    raise LarchError(e.code, text) from None
                wait = int((e.headers or {}).get("retry-after") or 0) or 5 * attempt
                print(f"  Larch {e.code}，等 {wait} 秒再試（第 {attempt} 次）", flush=True)
                self.sleep(wait)

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, body)

    def patch(self, path, body, etag):
        return self.request("PATCH", path, body, {"If-Match": etag})

    def delete(self, path, body=None):
        return self.request("DELETE", path, body)

    def put_board(self, project_id, board_id, body, etag):
        """整張白板覆寫。條件邊與同一出口的多條邊只有這條路保得住。"""
        return self.request("PUT", f"/projects/{project_id}/boards/{board_id}", body,
                            {"If-Match": etag} if etag else None)

    def replace_project(self, project_id, project, etag):
        """整份覆寫。project 必須是剛 GET 回來的整份，只改要改的欄位。"""
        return self.request("PUT", f"/projects/{project_id}", {"project": project}, {"If-Match": etag}, _whole_project=True)

    def patch_settings(self, project_id, changes, summary):
        """只改帶到的設定。先 GET 拿 revision 放 If-Match；不是最新會回 412。"""
        rev = self.get(f"/projects/{project_id}/settings")["revision"]
        return self.request("PATCH", f"/projects/{project_id}/settings",
                            {"summary": summary, "changes": changes}, {"If-Match": f'"{rev}"'})

    def publish(self, project_id, body):
        """把市集版更新成專案現在的內容。每次都會多一個版本，追蹤者也可能收到通知。"""
        return self.request("POST", f"/projects/{project_id}/publish", body, _publish=True)

    def upload_media(self, project_id, path, category="scene"):
        path = Path(path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        res = self.post(f"/projects/{project_id}/media", {
            "name": path.name, "mimeType": mime, "category": category,
            "base64": base64.b64encode(path.read_bytes()).decode()})
        asset = res.get("asset") or (res.get("assets") or [res])[0]
        return asset["url"]

    def refresh_share_link(self, project_id):
        res = self.post(f"/projects/{project_id}/share-link", {"permission": "view"})
        return res.get("playUrl") or res.get("url") or json.dumps(res, ensure_ascii=False)
