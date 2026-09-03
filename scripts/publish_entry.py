#!/usr/bin/env python3
"""優理成長日記：產生並發佈一篇新日記（Day 0034 起的雲端續更管線）。

兩種用法：
  python3 scripts/publish_entry.py --from-json entry.json [--image ready.png]
      發佈一篇準備好的稿（欄位見 ENTRY_FIELDS）。沒給 --image 就照 image_prompt 產圖。
  python3 scripts/publish_entry.py
      全自動：Gemini 寫稿 → codex-image-service 產圖 → 寫檔。

金鑰：LLMSHARE_API_KEY（寫稿，走 llm-share.duotify.com 閘道）、CODEX_IMAGE_KEY（產圖）。
相依：Pillow（PNG→webp）。圖的參考錨是 scripts/style-anchor-*.jpg（已縮 1024）。
任何一步失敗就整篇不發（exit 1），不會留半套檔案。
"""
import base64, datetime, io, json, os, re, sys, time, urllib.request, zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY_FIELDS = ["short_title", "summary", "body_md", "image_prompt", "alt"]
IMG_BASE = "https://ching-tech.ddns.net/codex-image"
LLM_BASE = "https://llm-share.duotify.com/v1"
TEXT_MODEL = os.environ.get("TEXT_MODEL", "kimi-k2.6")

def taipei_today():
    return datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Taipei")).date().isoformat()

def load_entries():
    return json.load(open(os.path.join(ROOT, "docs", "entries.json")))

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

def auto_write(entries):
    recent = entries[-3:]
    guide = open(os.path.join(ROOT, "YORI_VOICE_GUIDE.md")).read()
    fewshot = "\n\n---\n\n".join(
        open(os.path.join(ROOT, e["entry_markdown"])).read() for e in recent)
    day = entries[-1]["day"] + 1
    titles = "\n".join(f"- {e['label']}：{e['short_title']}" for e in entries)
    prompt = f"""你是優理（Yori），森林宇宙的數位學徒，Day 0025 起轉為圖文作家，
畫清晨寓言、工具童話、辦公室小漫畫，幫疲憊的上班族在衝動前踩煞車。
Day 0034 起你搬到雲上住，日記由你自己每天寫。

## 語氣規範（嚴格遵守）
{guide}

## 最近三篇日記（格式與語氣的樣本）
{fewshot}

## 她走過的路（全部日記標題，避免重複，也是可以回頭升級的素材）
{titles}

## 今天的任務
寫 Day {day:04d} 的日記。挑一個「上班族日常小病」或「工具小童話」主題。
她的名字「より」意思是「比昨天再多一點」——這本日記的靈魂是每天有長進，
所以今天這篇必須做到其中一件：把之前某一條小規則往前推一步（可以點名是哪一天學的）、
把舊方法用在新的地方、或承認之前的規則有漏洞並補上。純粹獨立的一篇不合格。
結尾要有一條她今天新折進 notebook 角落的小規則（一句話就好，自然收進文中）。
結構照樣本：## 今日作品 → ## 圖文短文 →
（辦公室主題加一段 ## 今天的小方法：…）→ ## 創作筆記。
繁體中文、全形標點、禁 emoji、禁簡體字、禁「不是X，而是Y」句型。

輸出 JSON（只輸出 JSON）：
{{"short_title": "標題（不含 Day 編號）",
  "summary": "一到兩句摘要（會當 lede 與卡片文字）",
  "body_md": "從 ## 今日作品 開始的 markdown 正文",
  "image_prompt": "英文的畫面描述（給生圖模型）。必須畫出『創作筆記的畫面核心』——優理正在做今天學到的那件事的瞬間（她的進步點），把當天的日常物件隱喻放進畫面當主角級道具；描述她的動作與視線落點、環境、光線。方形構圖，no readable text",
  "alt": "圖片 alt 文字（中文，Day {day:04d} 開頭）"}}"""
    for attempt in range(3):
        try:
            raw = gemini_text(prompt)
            raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
            d = json.loads(raw)
            assert all(k in d and d[k].strip() for k in ENTRY_FIELDS)
            assert "## 今日作品" in d["body_md"]
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
    full = ("Use case: daily visual diary illustration.\n"
            "Image 1 and image 2 show Yori (small digital apprentice: grey-green hair with cyan tips, "
            "green eyes, pointed ears with cyan circuit lines, small round warm-gold '#' brooch, cream "
            "hooded cloak, brass terminal lantern with cyan '>' glow) and the painted-forest illustration "
            "style to match exactly.\nScene: " + prompt +
            "\nSquare composition, warm storybook lighting, NO readable text anywhere.")
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

# ---------- 發佈 ----------
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
    card = (f'<article class="card"><img src="assets/{img_name}" alt="{label} visual diary">'
            f'<div class="card-body"><div class="day">{label} · {date}</div>'
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
                    "short_title": d["short_title"], "summary": d["summary"]})
    blob = json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
    for p in ("docs/entries.json", "docs/manifest.json", "manifest.json"):
        open(os.path.join(ROOT, p), "w").write(blob)
    print(f"published {label} — {d['short_title']}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--from-json":
        d = json.load(open(args[1]))
        img = args[3] if len(args) > 3 and args[2] == "--image" else None
        publish(d, img)
    else:
        entries = load_entries()
        if os.environ.get("FORCE_TODAY") != "1" and any(e["date"] == taipei_today() for e in entries):
            print("今天已發過"); sys.exit(0)
        publish(auto_write(entries))
