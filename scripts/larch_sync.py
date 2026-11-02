"""讓 Larch《格莉奇日記》跟 posts.json 一致。

每個月一個 board（m-YYYY-MM）：月曆 miniGame 卡當起點，點一天翻到那天的
對話卡（一篇一張，dialogueLines 一句一行、每句換立繪），講完接回月曆。
board-main 只有一張 boardJump，讀者按「開始遊戲」就到最新的月份。

每次都把每張 board 該長怎樣整份算出來，內容雜湊寫在 board 的 description；
跟 Larch 上的雜湊不同才整張覆寫（PUT /boards/:id），所以重跑不會多出任何卡，
某天失敗了下一班會自動補上，回填三個月也是同一支程式。
背景與立繪直接用 GitHub Pages 的網址，不上傳素材。

用法：python scripts/larch_sync.py [--config larch/config.json] [--dry-run]
"""
import argparse
import calendar
import datetime as dt
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import larch_pages
from scripts.larch_api import Larch

ROOT = Path(__file__).resolve().parent.parent
TZ = dt.timezone(dt.timedelta(hours=8))
log = logging.getLogger("larch_sync")
CAL_TPL = (ROOT / "larch" / "calendar.html").read_text("utf-8")
# 〈格莉奇 4KB〉放在格莉奇音樂站上；掛在月曆卡，翻頁時延續播放。音量壓低，玩家可在設定裡再調。
THEME_SONG = "https://yazelin.github.io/glitch-music/audio/glitch-4kb.mp3"
SPEAKER = "格莉奇"


def _ym(date):
    return date[:7]


def _cond(eid, source, target, value):
    return {"id": eid, "source": source, "target": target, "sourceHandle": "right",
            "data": {"condition": {"kind": "variable", "variable": "diary_go", "op": "eq", "value": value}}}


def _edge(eid, source, target):
    return {"id": eid, "source": source, "target": target, "sourceHandle": "right"}


def _actor(base, face):
    return {"actors": [{"id": "glitch", "url": f"{base}/larch/sprites/{face}.webp", "name": SPEAKER,
                        "slot": "right", "enter": "none", "scale": 1, "offsetX": 0, "offsetY": 0}]}


def cg_items(posts, base):
    """CG 收藏清單：網站日記本來的插畫，先上鎖，讀到那一天的頁面才解鎖。"""
    return [{"url": f"{base}/{p['image']}", "title": f"{p['date']} {p.get('title', '')}", "locked": True}
            for _, p in larch_pages.post_key(posts)
            if p.get("type") == "image" and p.get("image") and str(p.get("body", "")).strip()]


def calendar_data(year, month, entries, today, has_prev, has_next, base, start):
    days = {}
    for key, p in entries:
        img = p.get("image") if p.get("type") == "image" else None
        # 月曆格子用網站本來就有的 360px 縮圖，整個月才不會一次載十幾張大圖。
        thumb = f"{base}/images/posts/thumbs/{img.rsplit('/', 1)[-1]}" if img else None
        excerpt = None if thumb else "".join(str(p.get("body", "")).split())[:60]  # 文字日的格子放開頭一小段
        days.setdefault(str(int(p["date"][8:])), []).append(
            {"key": key, "title": p.get("title", ""), "thumb": thumb, "excerpt": excerpt})
    # 開始寫日記以後、今天以前，沒有日記的日子是產文失敗那天，月曆標「休息」。
    n = calendar.monthrange(year, month)[1]
    rest = [d for d in range(1, n + 1) if str(d) not in days and start < f"{year}-{month:02d}-{d:02d}" < today]
    # 今天只寫進自己那個月，舊月份的內容才不會每天都變、每天都重送。
    return {"year": year, "month": month, "today": today if _ym(today) == f"{year}-{month:02d}" else None,
            "prev": has_prev, "next": has_next, "days": days, "rest": rest,
            # 「看今天」按鈕只放最新的月份：月曆卡只連得到自己這個月的頁面
            "latest": None if has_next else (entries[-1][0] if entries else None)}


def _cal_html(data):
    return re.sub(r"/\*DATA\*/.*?/\*END\*/", lambda m: "/*DATA*/" + json.dumps(data, ensure_ascii=False) + "/*END*/",
                  CAL_TPL, count=1, flags=re.S)


def _board(name, nodes, edges):
    body = {"name": name, "nodes": nodes, "edges": edges}
    sha = hashlib.sha1(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {**body, "description": f"sync:{sha}"}


def build(posts, lines_for, today, base):
    """posts → {board_id: board body}。lines_for(key, post) 回傳 [{text, face}]。純函式。"""
    months = {}
    for key, p in larch_pages.post_key(posts):
        if not str(p.get("body", "")).strip():
            log.warning("%s 這篇內文是空的，先跳過", key)
            continue
        months.setdefault(_ym(p["date"]), []).append((key, p))
    order = sorted(months)
    start = min(p["date"] for _, p in months[order[0]]) if order else today
    boards = {}
    for i, ym in enumerate(order):
        y, m = int(ym[:4]), int(ym[5:])
        cal_id, entries = f"cal-{ym}", months[ym]
        prev_ym = order[i - 1] if i else None
        next_ym = order[i + 1] if i + 1 < len(order) else None
        nodes = [{"id": cal_id, "type": "story", "position": {"x": 0, "y": 0}, "data": {
            "type": "miniGame", "title": f"{y} 年 {m} 月", "text": "", "start": True,
            "miniGameHtml": _cal_html(calendar_data(y, m, entries, today, bool(prev_ym), bool(next_ym), base, start)),
            "miniGameReadVars": [], "miniGameWriteVars": ["diary_go"], "miniGamePresentation": "fullscreen",
            "bgm": THEME_SONG, "bgmVolume": 0.18, "bgmLoop": True,
            "miniGameFrame": {"showButton": False, "showTitle": False},
            "transition": "pageTurn", "transitionMs": 700, "stage": {"actors": []}, "characterLayers": []}}]
        edges = []
        for j, (key, p) in enumerate(entries):
            nid = "d-" + key[:10].replace("-", "") + key[10:]
            lines = lines_for(key, p)
            nodes.append({"id": nid, "type": "story", "position": {"x": 500 + (j % 6) * 360, "y": (j // 6) * 260},
                          "data": {"type": "dialogue", "title": f"{p['date']} {p.get('title', '')}", "speaker": SPEAKER,
                                   "text": lines[0]["text"], "background": f"{base}/larch/bg/{key}.webp",
                                   "transition": "pageTurn", "transitionMs": 700, "stage": _actor(base, lines[0]["face"]),
                                   **({"cgOps": [{"id": f"cg-{key}", "mode": "unlock", "url": f"{base}/{p['image']}"}]}
                                      if p.get("type") == "image" and p.get("image") else {}),
                                   "dialogueLines": [{"id": f"l{k}", "speaker": SPEAKER, "text": l["text"],
                                                      "stage": _actor(base, l["face"])} for k, l in enumerate(lines)]}})
            edges.append(_cond(f"e-{cal_id}-{nid}", cal_id, nid, key))
            edges.append(_edge(f"e-{nid}-back", nid, cal_id))
        for word, other in (("prev", prev_ym), ("next", next_ym)):
            if other:
                jid = f"jump-{ym}-{word}"
                nodes.append({"id": jid, "type": "story", "position": {"x": 0, "y": -300 if word == "prev" else 300},
                              "data": {"type": "boardJump", "title": "上個月" if word == "prev" else "下個月",
                                       "jumpBoardId": f"m-{other}", "jumpNodeId": f"cal-{other}", "stage": {"actors": []}}})
                edges.append(_cond(f"e-{cal_id}-{jid}", cal_id, jid, word))
        boards[f"m-{ym}"] = _board(f"{y} 年 {m} 月", nodes, edges)
    if order:
        latest = order[-1]
        boards["board-main"] = _board("開始", [{"id": "start-latest", "type": "story", "position": {"x": 0, "y": 0},
                                              "data": {"type": "boardJump", "title": "最新的月份", "start": True,
                                                       "jumpBoardId": f"m-{latest}", "jumpNodeId": f"cal-{latest}",
                                                       "stage": {"actors": []}}}], [])
    return boards


def plan(boards, remote):
    """要覆寫的 board，依序：新的月份先建、舊月份更新、board-main 最後（它指向的月份要先存在）。"""
    todo = [bid for bid, b in boards.items() if remote.get(bid) != b["description"]]
    return sorted(todo, key=lambda bid: (bid == "board-main", bid in remote, bid))


def apply(todo, boards, api, project_id, share):
    """逐張覆寫；中途失敗時已寫好的留著，下次 plan 會看到它們已經一致。"""
    for bid in todo:
        etag = api.get(f"/projects/{project_id}")["_etag"]
        api.put_board(project_id, bid, {**boards[bid], "summary": f"同步日記：{boards[bid]['name']}"}, etag)
        log.info("已更新 %s", bid)
    # 分享連結每班都刷：上一班 board 寫好了、只有刷新失敗時，重跑才補得回來。網址不會變。
    if share:
        return api.refresh_share_link(project_id)
    return None


def render_backgrounds(posts, bg_dir, root, render):
    """只產還沒有的背景。已經產過的不重產：Pillow 換版本時位元組會變，全部重寫會讓 repo 每次多十幾 MB。
    插畫檔不見時退回文字頁並警告，不讓一篇舊日記擋住每天的同步。"""
    bg_dir.mkdir(parents=True, exist_ok=True)
    for key, p in larch_pages.post_key(posts):
        out = bg_dir / f"{key}.webp"
        if out.exists() or not str(p.get("body", "")).strip():
            continue
        illu = root / p["image"] if p.get("type") == "image" and p.get("image") else None
        try:
            render(p, out, illu)
        except FileNotFoundError as e:
            log.warning("%s 的插畫檔找不到（%s），先用文字頁", key, e)
            render(p, out, None)


# 格莉奇手機：遊戲常駐 UI（HUD），角落一顆頭像，點開跟格莉奇聊天。原始碼在 larch/hud/。
# 從編輯器導入插件時 Larch 會把執行內容存進 settings.plugins[id].playback，這裡直接寫同樣的形狀。
HUD_ID = "glitch-phone"
CHAT_VARS = [
    # persistent＝跨週目保留：回到標題、重新開始都不重置，讀者下次來格莉奇還記得名字與上次的對話
    {"id": "glitch_reader_name", "name": "glitch_reader_name", "type": "string", "label": "讀者名字",
     "description": "格莉奇手機第一次打開時問的名字", "defaultValue": "", "persistent": True},
    {"id": "glitch_chat", "name": "glitch_chat", "type": "string", "label": "格莉奇手機對話",
     "description": "格莉奇手機的對話紀錄（JSON）", "defaultValue": "[]", "persistent": True},
]


def hud_plugin():
    names = [v["name"] for v in CHAT_VARS]
    return {"enabled": True, "playback": {
        "version": "1.0.0", "permissions": ["player:ui", "variables:read", "variables:write"], "defaults": {},
        "huds": [{"id": "phone", "title": "格莉奇手機", "anchor": "top-right", "width": 88, "height": 88,
                  "offsetX": 4, "offsetY": 44, "interactive": True, "readVariables": names, "writeVariables": names,
                  "html": (ROOT / "larch" / "hud" / "glitch-phone.html").read_text("utf-8")}]}}


def sync_project_meta(api, project_id, description, plugins, variables):
    """專案簡介（標題畫面也顯示）、插件與變數都只有整份 PUT 改得到，所以只在跟這裡不同時才做：
    讀整份、只改這幾項、帶 If-Match 推回。變數只補缺的，不動作者改過的預設值。
    整份 PUT 會清掉白板（larch-vn 筆記），回傳 True 時呼叫端要把白板全部重推。"""
    proj = api.get(f"/projects/{project_id}")
    etag = proj.pop("_etag")
    out = dict(proj)
    if description and proj.get("description") != description:
        out["description"] = description
    settings = proj.get("settings") or {}
    current = settings.get("plugins") or {}
    if any(current.get(k) != v for k, v in plugins.items()):
        out["settings"] = {**settings, "plugins": {**current, **plugins}}
    # 變數只補缺的；已經有的只校正「跨週目保留」（persistent），不動作者改過的預設值與標籤
    want = {v["name"]: v for v in variables}
    have = proj.get("variables") or []
    fixed = [{**v, "persistent": want[v.get("name")]["persistent"]}
             if v.get("name") in want and "persistent" in want[v.get("name")]
             and v.get("persistent") != want[v.get("name")]["persistent"] else v for v in have]
    names = {v.get("name") for v in have}
    fixed += [v for v in variables if v["name"] not in names]
    if fixed != have:
        out["variables"] = fixed
    if out == proj:
        return False
    api.replace_project(project_id, out, etag)
    log.info("已更新專案設定：%s", ", ".join(k for k in out if out[k] != proj.get(k)))
    return True


def sync_cg(api, project_id, items):
    """插畫收藏只補 Larch 上還沒有的網址（addCgGalleryItems 本身也會略過重複的）。"""
    have = {i.get("url") for i in api.get(f"/projects/{project_id}/settings")["settings"].get("cgGalleryItems") or []}
    new = [i for i in items if i["url"] not in have]
    if new:
        api.patch_settings(project_id, {"addCgGalleryItems": new}, f"插畫收藏加入 {len(new)} 張")
        log.info("插畫收藏加入 %d 張", len(new))
    return new


def publish_body(boards, posts, today, description):
    """每晚重新上架帶的內容。介紹每次都要帶：沒帶的話商店頁會換成專案簡介（標題畫面那段短版）。
    公開白板帶全部，下個月的新白板才會自動公開。其他商店欄位（封面、標籤、AI 揭露）沿用上一次。
    只有當天日記有插畫才通知追蹤者，平常的日子靜靜更新（作者 2026-10-31 決定）。"""
    new = [p for _, p in larch_pages.post_key(posts) if p["date"] == today and str(p.get("body", "")).strip()]
    note = "、".join(f"〈{p.get('title', '')}〉" for p in new)
    return {"description": description,
            "publishedBoardIds": ["board-main"] + sorted(b for b in boards if b != "board-main"),
            "startBoardId": "board-main",
            "updateNote": f"新增 {int(today[5:7])}/{int(today[8:])} 的日記{note}" if new else "更新日記內容",
            "notifyFollowers": any(p.get("type") == "image" and p.get("image") for p in new)}


def published_today(api, project_id, today):
    """市集版今天（台北時間）已經更新過就不再上架，手動重跑同步也只會上架一次。"""
    for w in api.get("/published").get("works") or []:
        if w.get("projectId") == project_id:
            at = dt.datetime.fromisoformat(w["updatedAt"].replace("Z", "+00:00")).astimezone(TZ)
            return at.date().isoformat() == today
    return False


def remote_descriptions(api, project_id):
    proj = api.get(f"/projects/{project_id}")
    return {b["id"]: b.get("description") or "" for b in proj.get("boards", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "larch" / "config.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = json.loads(Path(args.config).read_text("utf-8"))
    posts = json.loads((ROOT / "posts.json").read_text("utf-8"))

    from scripts import generate_post, larch_page_image
    ask = lambda prompt: generate_post.ask("gemini-2.5-flash", prompt, json_mode=True)
    pages_dir, bg_dir = ROOT / "larch" / "pages", ROOT / "larch" / "bg"

    def lines_for(key, p):
        return larch_pages.load_or_split(key, p, ask, pages_dir)

    render_backgrounds(posts, bg_dir, ROOT, larch_page_image.render_page)

    today = dt.datetime.now(TZ).date().isoformat()
    boards = build(posts, lines_for, today, cfg["base_url"])
    api = Larch(os.environ["LARCH_AGENT_KEY"])
    pid = cfg["project_id"]
    if args.dry_run:
        todo = plan(boards, remote_descriptions(api, pid))
        print(f"要更新 {len(todo)} 張 board：{', '.join(todo) or '（沒有）'}", flush=True)
        return
    replaced = sync_project_meta(api, pid, cfg.get("description"), {HUD_ID: hud_plugin()}, CHAT_VARS)
    sync_cg(api, pid, cg_items(posts, cfg["base_url"]))
    todo = plan(boards, {} if replaced else remote_descriptions(api, pid))
    print(f"要更新 {len(todo)} 張 board：{', '.join(todo) or '（沒有）'}", flush=True)
    url = apply(todo, boards, api, pid, cfg.get("share", False))
    if replaced:  # 整份推過，讀回來確認白板都在
        missing = set(boards) - set(remote_descriptions(api, pid))
        if missing:
            raise SystemExit(f"整份推回後少了白板：{sorted(missing)}")
    if url:
        print(f"分享連結：{url}", flush=True)
    # 市集版是上架當下的快照，白板有變才重新上架，一天最多一次
    if cfg.get("publish") and todo:
        if published_today(api, pid, today):
            print("市集版今天已經更新過，不再上架", flush=True)
        else:
            api.publish(pid, publish_body(boards, posts, today, (ROOT / "larch" / "listing.md").read_text("utf-8").strip()))
            print("已重新上架市集", flush=True)


if __name__ == "__main__":
    main()
