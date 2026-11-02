"""優理的圖文日記 → Larch 作品《優理的圖文日記》。每晚發完日記後跑一次。

沿用格莉奇日記的 larch_sync：每月一張白板、月曆 miniGame 點一天翻到那天，一篇一張對話卡。
這裡換掉的部分：背景是日記頁（larch_page），四格漫畫逐句放大對到的那一格；
每句由模型看圖挑格子與優理的表情（larch_faces，快取在 larch/faces/）。

用法：python scripts/larch_yori.py [--dry-run] [--local project.json]
  --local 只產專案 JSON 給本機 larch-preview 看，不連 Larch。
"""
import argparse
import base64
import json
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts import larch_faces, larch_page, larch_pages, larch_sync  # noqa: E402
from scripts.larch_api import Larch  # noqa: E402
from scripts.larch_panels import find_panels  # noqa: E402

CFG = json.loads((ROOT / "larch/config.json").read_text("utf-8"))
BASE = CFG["base_url"]
BG, FACE_CACHE = ROOT / "docs/larch/bg", ROOT / "larch/faces"
BODY_HEADS = ("圖文短文", "Yori 的日記", "今天的日記")
POSES = {"draw", "phone", "mug", "hug"}  # 動作立繪手上沒有燈
log = logging.getLogger("larch_yori")


def body_of(md):
    for h in BODY_HEADS:
        m = re.search(rf"^## {re.escape(h)}\s*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
        if m:
            return m.group(1).strip()
    return ""


def posts():
    out = []
    for e in json.loads((ROOT / "docs/entries.json").read_text("utf-8")):
        md = (ROOT / e["entry_markdown"]).read_text("utf-8")
        out.append({"date": e["date"], "title": e.get("short_title") or e["title"], "body": body_of(md),
                    "type": "image", "image": e["image"].removeprefix("docs/"), "day": e["day"],
                    "comic": "Four-panel" in md})
    return [p for p in out if p["body"]]


def _actor(base, face):
    a = lambda i, url, loop: {"id": i, "url": url, "name": "優理", "slot": "right", "enter": "none", "scale": 1,
                              "offsetX": 0, "offsetY": 0, "loop": loop, "loopSpeed": 0.6, "loopStrength": 0.6}
    yori = a("yori", f"{base}/larch/sprites/{face}.webp", "none")
    if face in POSES:
        return {"actors": [yori]}
    # 優理一定排第一：Larch 把第一個 actor 當主角，其他的會調暗
    return {"actors": [yori, a("lamp-halo", f"{base}/larch/sprites/fx-halo.webp", "pulse")]}


def build(ps, ask=True):
    """回傳 {board_id: board}。順手補還沒產的背景、還沒挑的格子與表情。"""
    keyed = list(larch_pages.post_key(ps))
    boxes = {}
    for key, p in keyed:
        src = ROOT / "docs" / p["image"]
        boxes[key] = find_panels(src) if p["comic"] else None
        if p["comic"] and not boxes[key]:
            log.warning("%s 找不到四格的格子，整篇只放整張", key)
        for i in [None] + ([1, 2, 3, 4] if boxes[key] else []):
            out = BG / (f"{key}.webp" if i is None else f"{key}-p{i}.webp")
            if not out.exists():
                BG.mkdir(parents=True, exist_ok=True)
                larch_page.render(p, out, src, i, boxes[key])

    line_cache = {}

    def lines_for(key, p):
        if key in line_cache:
            return line_cache[key]
        lines = larch_pages.fallback_split(p["body"])
        picks = larch_faces.pick(key, [l["text"] for l in lines], ROOT / "docs" / p["image"], FACE_CACHE, ask=ask)
        out = []
        for i, (l, k) in enumerate(zip(lines, picks)):
            # 0 是回到整張（四格沒畫的心得句）；第一句一定從格子開場，挑 0 或沒挑就放第 1 格
            panel = k["panel"] if i else (k["panel"] or 1)
            out.append({**l, "face": k["face"], **({"panel": panel} if boxes[key] and panel is not None else {})})
        return line_cache.setdefault(key, out)

    larch_sync.SPEAKER = ""
    larch_sync._actor = _actor
    larch_sync.THEME_SONG = None
    cal_data = larch_sync.calendar_data
    by_key = dict(keyed)

    def calendar_data(*a):
        data = cal_data(*a)
        for day in data["days"].values():
            for q in day:  # 每篇都有圖：縮圖換成這個站的
                d = by_key[q["key"]]
                q["thumb"], q["excerpt"] = f"{BASE}/assets/thumbs/{d['image'].rsplit('/', 1)[-1]}", None
                q["img"], q["day"], q["comic"] = f"{BASE}/{d['image']}", d["day"], d["comic"]
        return data
    larch_sync.calendar_data = calendar_data
    forest = base64.b64encode((ROOT / "larch/forest.jpg").read_bytes()).decode()
    larch_sync.CAL_TPL = larch_sync.CAL_TPL.replace("__FOREST__", "data:image/jpeg;base64," + forest)

    boards = larch_sync.build(ps, lines_for, ps[-1]["date"], BASE)
    by_title = {f"{p['date']} {p['title']}": k for k, p in keyed}
    for b in boards.values():
        for n in b["nodes"]:
            d = n["data"]
            d.pop("bgm", None)
            k = by_title.get(d.get("title"))
            if d.get("type") != "dialogue" or not k:
                continue
            d["visualEffects"] = [{"id": "embers", "intensity": 0.45, "speed": 0.5, "tint": "#ecc874"}]  # 螢火蟲
            for dl, l in zip(d["dialogueLines"], line_cache[k]):
                dl["text"] = dl["text"].strip()  # 原文段落裡的斷行會留在句首
                if "panel" in l:
                    dl["background"] = f"{BASE}/larch/bg/{k}" + (f"-p{l['panel']}" if l["panel"] else "") + ".webp"
            if "background" in d["dialogueLines"][0]:  # 進卡時播放器用卡片背景，第一句自己的背景不生效
                d["background"] = d["dialogueLines"][0]["background"]
        # description 是內容雜湊，plan() 拿它判斷要不要重推；上面改過節點，要重算
        b["description"] = larch_sync._board(b["name"], b["nodes"], b["edges"])["description"]
    return boards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", help="只寫專案 JSON 到這個路徑（素材走相對路徑），不連 Larch")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ps = posts()
    if args.local:
        global BASE
        BASE = "."
    boards = build(ps, ask=not args.local)
    if args.local:
        proj = {"name": "優理的圖文日記", "boards": [{"id": k, **v} for k, v in
                                                     sorted(boards.items(), key=lambda kv: kv[0] != "board-main")]}
        Path(args.local).write_text(json.dumps(proj, ensure_ascii=False), "utf-8")
        print(len(ps), "篇", sorted(boards))
        return
    today = ps[-1]["date"]  # 用最新一篇的日期：排程晚到隔天也不會把日記算錯天
    api, pid = Larch(os.environ["LARCH_AGENT_KEY"]), CFG["project_id"]
    if args.dry_run:
        todo = larch_sync.plan(boards, larch_sync.remote_descriptions(api, pid))
        print(f"要更新 {len(todo)} 張 board：{', '.join(todo) or '（沒有）'}", flush=True)
        return
    replaced = larch_sync.sync_project_meta(api, pid, CFG.get("description"), {}, [])
    larch_sync.sync_cg(api, pid, larch_sync.cg_items(ps, BASE))
    todo = larch_sync.plan(boards, {} if replaced else larch_sync.remote_descriptions(api, pid))
    print(f"要更新 {len(todo)} 張 board：{', '.join(todo) or '（沒有）'}", flush=True)
    url = larch_sync.apply(todo, boards, api, pid, CFG.get("share", False))
    missing = set(boards) - set(larch_sync.remote_descriptions(api, pid))
    if missing:
        raise SystemExit(f"推完少了白板：{sorted(missing)}")
    if url:
        print(f"分享連結：{url}", flush=True)
    if CFG.get("publish") and todo:  # 市集版是上架當下的快照，白板有變才重新上架，一天最多一次
        if larch_sync.published_today(api, pid, today):
            print("市集版今天已經更新過，不再上架", flush=True)
        else:
            api.publish(pid, larch_sync.publish_body(boards, ps, today, (ROOT / "larch/listing.md").read_text("utf-8").strip()))
            print("已重新上架市集", flush=True)


if __name__ == "__main__":
    main()
