#!/usr/bin/env python3
"""優理成長日記：產生並發佈一篇新日記（Day 0034 起的雲端續更管線）。

兩種用法：
  python3 scripts/publish_entry.py --from-json entry.json [--image ready.png]
      發佈一篇準備好的稿（欄位見 ENTRY_FIELDS）。沒給 --image 就照 image_prompt 產圖。
  python3 scripts/publish_entry.py
      全自動：看今天新聞找靈感 → 寫稿 → codex-image-service 畫四格 → 寫檔。
  DRY_RUN=1 python3 scripts/publish_entry.py
      只把稿與圖寫進 drafts/dry-run/，不動站上任何檔。

金鑰：LLMSHARE_API_KEY（寫稿，走 llm-share.duotify.com 閘道）、CODEX_IMAGE_KEY（產圖）、
GEMINI_API_KEY（gmw_ 開頭，看新聞用 gemini-web 的 Google 搜尋；缺了或失敗就不看新聞照寫）。

2026-09-24 改版：Day 0034–0056 只餵自己的舊日記、又強制每篇接著升級前一條規則，
結果連續十幾天都在寫「寄信前還要檢查某個舊東西」，圖也全是同一張雲上書桌。
改成每天從新聞拿靈感（照格莉奇日記與 catime 的做法）、題材分類加冷卻、範本固定用
幾篇風格差異大的舊作、圖改回四格漫畫。
相依：Pillow（PNG→webp）。圖的參考錨是 scripts/style-anchor-*.jpg（已縮 1024）。
任何一步失敗就整篇不發（exit 1），不會留半套檔案。
"""
import base64, datetime, io, json, os, re, sys, time, urllib.request, zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY_FIELDS = ["short_title", "summary", "body_md", "image_prompt", "alt"]
IMG_BASE = "https://ching-tech.ddns.net/codex-image"
LLM_BASE = "https://llm-share.duotify.com/v1"
TEXT_MODEL = os.environ.get("TEXT_MODEL", "kimi-k2.6")
GEMINI_WEB_BASE = os.environ.get("GEMINI_WEB_BASE_URL", "https://ching-tech.ddns.net/gemini-web").rstrip("/")
DRY = os.environ.get("DRY_RUN") == "1"
# 題材分類：最近 COOLDOWN 篇用過的分類當天不能再選。開發日誌只給 Day 0000–0024 那段舊紀錄用。
CATEGORIES = ["信件", "檔案", "待辦與時間", "會議與溝通", "工具與電腦", "休息與心情", "寓言"]
COOLDOWN = 3
# 範本固定用這幾篇（格式與語氣），不再餵最近三篇：餵最近的會把題材一路鎖死。
FEWSHOT_DAYS = [27, 30, 33]

def taipei_today():
    return datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Taipei")).date().isoformat()

def load_entries():
    return json.load(open(os.path.join(ROOT, "docs", "entries.json")))

RULES_PATH = os.path.join(ROOT, "scripts", "rules.json")

def load_rules():
    return json.load(open(RULES_PATH))

def save_rules(rules):
    json.dump(rules, open(RULES_PATH, "w"), ensure_ascii=False, indent=1)

# ---------- markdown → html（老日記只用 h2 / p / ul） ----------
def md2html(md):
    out, ul = [], []
    def flush_ul():
        if ul:
            out.append("<ul>\n" + "\n".join(f"<li>{x}</li>" for x in ul) + "\n</ul>")
            ul.clear()
    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush_ul(); continue
        if s.startswith("## "):
            flush_ul(); out.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("- "):
            ul.append(s[2:])
        else:
            flush_ul(); out.append(f"<p>{s}</p>")
    flush_ul()
    return "\n".join(out)

# ---------- llmshare 寫稿（OpenAI 協議） ----------
def gemini_text(prompt):  # 名字留著少動呼叫端；後端已換 llmshare
    key = os.environ["LLMSHARE_API_KEY"]
    body = {"model": TEXT_MODEL, "temperature": 0.9,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(LLM_BASE + "/chat/completions",
        json.dumps(body).encode(),
        {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    return r["choices"][0]["message"]["content"]

def fetch_news(recent_news):
    """今天的新聞摘要清單。跟格莉奇日記、catime 同一套：失敗就回空清單，當天改自由發揮。"""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("沒有 GEMINI_API_KEY，今天不看新聞", file=sys.stderr); return []
    prompt = ("Search for today's news that an office worker in Taiwan would chat about at lunch: "
              "workplace, tech tools, apps, AI at work, commuting, food, weather, health, lifestyle, "
              "quirky or heartwarming stories. Mix Taiwan and international.\n"
              "At most ONE item about AI, big tech companies or business deals. Prefer small, relatable "
              "stories with a picture in them: food, commuting, weather, pets, app glitches, office habits, "
              "a new product people argue about, a funny survey result.\n"
              "AVOID: war, terrorism, political fights, violent crime, disasters with casualties.\n"
              "Pick 5 items. For each, write a 1-sentence summary in 繁體中文 with a concrete detail. "
              "Do not use ASCII double quotes inside the summaries; use 「」 instead.\n"
              "Skip anything similar to these recent ones: " + json.dumps(recent_news[-20:], ensure_ascii=False) + "\n"
              'Output JSON only: {"news": ["摘要 1", "摘要 2", ...]}')
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                f"{GEMINI_WEB_BASE}/v1beta/models/gemini-2.5-flash:generateContent",
                json.dumps(body).encode(),
                {"Content-Type": "application/json", "x-goog-api-key": key})
            d = json.load(urllib.request.urlopen(req, timeout=180))
            raw = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
            m = re.search(r"\{.*\}", raw, re.S)
            news = json.loads(m.group(0), strict=False)["news"] if m else None
            if isinstance(news, list) and len(news) >= 3:  # 只回一兩則通常是把幾件事擠成一句
                return [str(x) for x in news[:5]]
        except Exception as e:
            print(f"看新聞第 {attempt+1} 次失敗：{e}", file=sys.stderr)
        time.sleep(5)
    print("今天不看新聞，自由發揮", file=sys.stderr)
    return []

def auto_write(entries):
    guide = open(os.path.join(ROOT, "YORI_VOICE_GUIDE.md")).read()
    fewshot = "\n\n---\n\n".join(
        open(os.path.join(ROOT, e["entry_markdown"])).read()
        for e in entries if e["day"] in FEWSHOT_DAYS)
    day = entries[-1]["day"] + 1
    rules = load_rules()
    ledger = "\n".join(f"- Day {r['day']:04d}：{r['rule']}" for r in rules)
    recent_titles = "\n".join(f"- {e['label']}：{e['short_title']}" for e in entries[-14:])
    used = [e.get("inspiration") for e in entries if e.get("inspiration")]
    news = fetch_news(used)
    cooling = [c for c in (e.get("category") for e in entries[-COOLDOWN:]) if c]
    allowed = [c for c in CATEGORIES if c not in cooling]
    consolidation = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Taipei")).day == 1
    news_block = ("## 今天的新聞（挑一則當靈感，轉成上班族日常的一個小場面；不要照抄新聞，也不要評論新聞）\n"
                  + "\n".join(f"- {n}" for n in news)) if news else \
                 "## 今天沒有新聞可看\n從上班族日常自己找一個小場面。"
    task = ("今天是每月的『整理日』。回顧上面的規則帳本，挑兩三條相近或已經升級過的規則折併成更短的一條，"
            "寫一篇整理日日記：講他攤開 notebook 整理便條的過程、哪幾條併成了什麼、哪一條其實已經長進身體裡不用再寫。"
            "這篇的四格漫畫畫他整理便條的過程。") if consolidation else (
            f"寫 Day {day:04d} 的日記。題材分類只能從這幾個選：{'、'.join(allowed)}"
            f"（{'、'.join(cooling) or '無'} 最近剛寫過，今天不選）。"
            "他的名字「より」意思是「比昨天再多一點」，長進要算在作者的手藝上：這次的笑點、分鏡、角色反應、"
            "或看事情的角度，要有一個是前面的日記沒試過的。規則帳本是參考，可以回頭用舊規則，"
            "但不要接著最近幾天的規則往下推，也不要又寫一條「寄出前還要檢查什麼」。"
            "結尾一樣收一條他今天新折進 notebook 角落的小規則（一句話，自然收進文中，不要跟帳本裡的重複）。"
            "這條規則不要用「……之後，還要……，不然……」的句型，帳本裡已經幾十條都長這樣了。")
    prompt = f"""你是優理（Yori），森林宇宙的數位學徒，Day 0025 起轉為圖文作家，
畫清晨寓言、工具童話、辦公室小漫畫，幫疲憊的上班族在衝動前踩煞車。
Day 0034 起你搬到雲上住，日記由你自己每天寫。每篇日記的主角作品是一則四格漫畫。

## 語氣規範（嚴格遵守）
{guide}

## 三篇舊作（只學格式與語氣，題材不要跟它們一樣）
{fewshot}

{news_block}

## notebook 角落的小規則帳本（參考用，別寫重複的規則）
{ledger}

## 最近十四天的標題（避免撞題）
{recent_titles}

## 今天的任務
{task}
結構照樣本：## 今日作品 → ## 圖文短文 →
（辦公室主題加一段 ## 今天的小方法：…）→ ## 創作筆記。
創作筆記的「類型」寫 Four-panel comic / 四格漫畫。
繁體中文、全形標點、禁 emoji、禁簡體字、禁「不是X，而是Y」句型。優理的代稱用中性的「他」。

輸出 JSON（只輸出 JSON，字串內不要用半形雙引號，引用改用「」）：
{{"short_title": "標題（不含 Day 編號）",
  "summary": "一到兩句摘要（會當 lede 與卡片文字）",
  "body_md": "從 ## 今日作品 開始的 markdown 正文",
  "category": "題材分類，只能填：{'、'.join(allowed if not consolidation else CATEGORIES)} 其中一個",
  "inspiration": "{'你選中的那則新聞原文（原樣複製）' if news else '沒有新聞，填空字串'}",
  "new_rule": "今天新折進 notebook 的那條小規則（一句話，40 字內）{'；整理日則改填折併後的規則' if consolidation else ''}",
  "merged_days": {"[被折併的舊規則 day 編號陣列，例如 [30, 31]；沒有就給空陣列]" if consolidation else "[]（今天不是整理日，固定給空陣列）"},
  "image_prompt": "英文的四格漫畫分鏡（給生圖模型）：依序寫 Panel 1 到 Panel 4，每格寫畫面、優理或其他角色的動作與表情，對白用繁體中文寫在引號「」裡（每格最多一句、十五字內）。第四格是反轉或笑點。場景跟著故事走，不要每天都在雲上書桌。",
  "alt": "圖片 alt 文字（中文，Day {day:04d} 開頭）"}}"""
    for attempt in range(3):
        try:
            raw = gemini_text(prompt)
            raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
            d = json.loads(raw, strict=False)
            assert all(k in d and str(d[k]).strip() for k in ENTRY_FIELDS)
            assert "## 今日作品" in d["body_md"]
            assert d.get("new_rule", "").strip(), "缺 new_rule"
            if d.get("category") not in CATEGORIES:
                d["category"] = allowed[0]
            return d
        except Exception as e:
            print(f"寫稿第 {attempt+1} 次失敗：{e}", file=sys.stderr)
            time.sleep(10)
    sys.exit(1)

# ---------- codex-image-service 產圖 ----------
def gen_image(prompt, out_path):
    key = os.environ["CODEX_IMAGE_KEY"]
    refs = []
    for name in ("style-anchor-a.jpg", "style-anchor-b.jpg"):
        p = os.path.join(ROOT, "scripts", name)
        refs.append(base64.b64encode(open(p, "rb").read()).decode())
    full = ("Use case: a four-panel comic (yonkoma) for a daily diary.\n"
            "Image 1 is the character sheet for Yori (small digital apprentice: grey-green hair with cyan tips, "
            "green eyes, pointed ears with cyan circuit lines, small round warm-gold '#' brooch, cream "
            "hooded cloak, brass terminal lantern with cyan '>' glow). Keep Yori's design exactly.\n"
            "Image 2 shows the comic FORMAT to follow: four numbered panels in a 2x2 grid, a short title "
            "banner, speech bubbles with Traditional Chinese text, clean line art with soft warm colors. "
            "Follow its layout and rendering only; do NOT copy its story, props or scene.\n"
            "Comic script:\n" + prompt +
            "\nSquare 2x2 four-panel layout. All dialogue in Traditional Chinese, short and legible, "
            "spelled exactly as written in the script. Settings change with the story.")
    body = {"prompt": full, "size": "1024x1024", "quality": "high", "count": 1,
            "reference_images_base64": refs}
    H = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    req = urllib.request.Request(IMG_BASE + "/v1/images/jobs", json.dumps(body).encode(), H)
    job = json.load(urllib.request.urlopen(req, timeout=120))
    jid = job.get("id") or job.get("request_id")
    for _ in range(40):  # 最多等 20 分鐘
        time.sleep(30)
        r = json.load(urllib.request.urlopen(
            urllib.request.Request(f"{IMG_BASE}/v1/images/jobs/{jid}", headers=H), timeout=60))
        st = r.get("status")
        if st == "succeeded":
            imgs = r.get("images") or r.get("data") or []
            b64 = imgs[0].get("b64_json") or imgs[0].get("base64")
            if b64:
                raw = base64.b64decode(b64)
            else:
                url = imgs[0]["url"]
                if url.startswith("/"): url = IMG_BASE + url
                raw = urllib.request.urlopen(url, timeout=120).read()
            _save_webp(raw, out_path)
            return
        if st in ("failed", "error"):
            print("產圖失敗：", json.dumps(r)[:300], file=sys.stderr); sys.exit(1)
    print("產圖逾時", file=sys.stderr); sys.exit(1)

def _save_webp(raw_bytes, out_path):
    """站上一律 webp（PNG 直出一張 1MB 級，36 張把首頁壓到 94MB，2026-09-03 踩過）。"""
    from PIL import Image
    im = Image.open(io.BytesIO(raw_bytes))
    im.save(out_path, "WEBP", quality=85, method=6)
    # 首頁卡片用 480px 縮圖：原圖 1254px 平均 280KB，57 張直接掛首頁是 16MB（2026-09-24 量到）
    thumb = os.path.join(os.path.dirname(out_path), "thumbs", os.path.basename(out_path))
    if "/docs/assets/" in out_path.replace(os.sep, "/"):
        os.makedirs(os.path.dirname(thumb), exist_ok=True)
        im.thumbnail((480, 480))
        im.save(thumb, "WEBP", quality=80, method=6)

# ---------- 發佈 ----------
def dry_run(d):
    out = os.path.join(ROOT, "drafts", "dry-run")
    os.makedirs(out, exist_ok=True)
    json.dump(d, open(os.path.join(out, "entry.json"), "w"), ensure_ascii=False, indent=1)
    gen_image(d["image_prompt"], os.path.join(out, "comic.webp"))
    print(json.dumps(d, ensure_ascii=False, indent=1))

def publish(d, image_path=None):
    entries = load_entries()
    day = entries[-1]["day"] + 1
    date = taipei_today()
    if os.environ.get("FORCE_TODAY") != "1" and any(e["date"] == date for e in entries):
        print(f"{date} 已有日記，跳過"); return
    label = f"Day {day:04d}"
    slug = f"day-{day:04d}"
    img_name = f"{slug}-yori-growth-log.webp"
    img_path = os.path.join(ROOT, "docs", "assets", img_name)

    # 1) 圖先到位（失敗就整篇不發）
    if image_path:
        _save_webp(open(image_path, "rb").read(), img_path)
    else:
        gen_image(d["image_prompt"], img_path)

    # 2) md
    md = f"# {label} — {d['short_title']}\n\n{d['body_md'].strip()}\n"
    open(os.path.join(ROOT, "docs", "entries", f"{slug}.md"), "w").write(md)

    # 3) html
    prev = entries[-1]
    prev_slug = os.path.basename(prev["entry"])
    tpl = open(os.path.join(ROOT, "scripts", "entry_template.html")).read()
    html = (tpl.replace("{{TITLE_FULL}}", f"{label} — {d['short_title']}")
               .replace("{{SELF_FILE}}", f"{slug}.html")
               .replace("{{DAY_LABEL}}", label).replace("{{DATE}}", date)
               .replace("{{TITLE_SHORT}}", d["short_title"])
               .replace("{{SUMMARY}}", d["summary"])
               .replace("{{IMG_NAME}}", img_name).replace("{{ALT}}", d["alt"])
               .replace("{{BODY_HTML}}", md2html(d["body_md"]))
               .replace("{{OLDER_FILE}}", prev_slug)
               .replace("{{OLDER_LABEL}}", prev["label"]))
    open(os.path.join(ROOT, "docs", "entries", f"{slug}.html"), "w").write(html)

    # 4) 前一篇的 entry-nav 換成 newer 連結
    prev_file = os.path.join(ROOT, prev["entry"])
    ph = open(prev_file).read()
    ph = ph.replace('<a href="../index.html">latest index →</a>',
                    f'<a href="{slug}.html">newer: {label} →</a>', 1)
    open(prev_file, "w").write(ph)

    # 5) index：hero 圖、badge 範圍、插新卡
    idx_file = os.path.join(ROOT, "docs", "index.html")
    idx = open(idx_file).read()
    idx = re.sub(r'(<figure class="hero-card"><img src=")assets/[^"]+(")',
                 rf"\g<1>assets/{img_name}\g<2>", idx, count=1)
    idx = re.sub(r'Day 0000–\d{4}[^<]*', f'Day 0000–{day:04d} entries', idx, count=1)
    idx = re.sub(r'href="entries/day-\d{4}\.html">Latest', f'href="entries/{slug}.html">Latest', idx, count=1)
    cat = d.get("category") or ""
    card = (f'<article class="card" data-date="{date}" data-cat="{cat}"><img src="assets/thumbs/{img_name}" loading="lazy" decoding="async" width="480" height="480" alt="{label} visual diary">'
            f'<div class="card-body"><div class="day">{label} · {date} · {cat}</div>'
            f'<h3>{d["short_title"]}</h3><p>{d["summary"]}</p>'
            f'<a class="read" href="entries/{slug}.html">讀這一天 →</a></div></article>')
    idx = idx.replace('<div class="grid">', '<div class="grid">' + card, 1)
    open(idx_file, "w").write(idx)

    # 6) 三份 JSON 鏡像
    entries.append({"day": day, "date": date, "title": f"{label} — {d['short_title']}",
                    "entry": f"docs/entries/{slug}.html",
                    "entry_markdown": f"docs/entries/{slug}.md",
                    "image": f"docs/assets/{img_name}",
                    "status": "cloud-auto", "label": label,
                    "short_title": d["short_title"], "summary": d["summary"],
                    "category": d.get("category", ""), "inspiration": d.get("inspiration", "")})
    blob = json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
    for p in ("docs/entries.json", "docs/manifest.json", "manifest.json"):
        open(os.path.join(ROOT, p), "w").write(blob)
    # 小規則帳本：追加今天的規則；整理日把被折併的舊條目移除
    if d.get("new_rule"):
        rules = load_rules()
        merged = set(d.get("merged_days") or [])
        if merged:
            rules = [r for r in rules if r["day"] not in merged]
        rules.append({"day": day, "rule": d["new_rule"].strip()})
        save_rules(rules)

    print(f"published {label} — {d['short_title']}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--from-json":
        d = json.load(open(args[1]))
        img = args[3] if len(args) > 3 and args[2] == "--image" else None
        publish(d, img)
    else:
        entries = load_entries()
        if not DRY and os.environ.get("FORCE_TODAY") != "1" and any(e["date"] == taipei_today() for e in entries):
            print("今天已發過"); sys.exit(0)
        d = auto_write(entries)
        dry_run(d) if DRY else publish(d)
