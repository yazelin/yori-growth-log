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
# 2026-10-01 從 kimi-k2.6 換成 deepseek-v4.1-flash：六個模型同題比較，它 36 秒寫完、引用的便條全對得上帳本；
# kimi 要 225 秒，還寫出前後矛盾的一篇（比較稿在 yaze-journal wednesday-live/素材-1007/優理寫稿比較-1001.md）
TEXT_MODEL = os.environ.get("TEXT_MODEL", "deepseek-v4.1-flash")
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

# 手藝經驗（2026-11-02）：寫完當天的稿，審稿一步挑毛病、寫成一句心得存進來；隔天寫四格與日記時讀。
# 每月整理日把心得折成最多八條原則。長進靠這份檔案累積，日記本身不寫創作過程。
CRAFT_PATH = os.path.join(ROOT, "scripts", "craft.json")
GAG_TYPES = ["期待落空", "優理一句點破", "情境本身荒謬", "優理巧妙解決", "拉遠揭露"]

def load_craft():
    try:
        return json.load(open(CRAFT_PATH))
    except FileNotFoundError:
        return {"principles": [], "notes": []}

def craft_block(craft):
    lines = [f"- {x}" for x in craft["principles"]] + \
            [f"- Day {n['day']:04d}：{n['lesson']}" for n in craft["notes"][-10:]]
    return ("## 你過去累積的手藝經驗（用在作品的寫法上，作品內容照常講故事）\n" + "\n".join(lines)) if lines else ""

def ask_json(prompt, check, what):
    for attempt in range(3):
        try:
            d = json.loads(re.sub(r"^```json\s*|\s*```$", "", gemini_text(prompt).strip()), strict=False)
            assert check(d)
            return d
        except Exception as e:
            print(f"{what}第 {attempt+1} 次失敗：{e}", file=sys.stderr)
            time.sleep(10)
    return None

def critique(d):
    """審今天的稿，回一則心得（失敗回 None，不擋發佈）。"""
    prompt = f"""你是嚴格的四格漫畫與中文編輯，拿下面的標準對照這篇日記與它的四格分鏡，找出差距。
{GAG_RULES}

## 文字的標準
{PLAIN_RULES}

## 四格分鏡
{d['image_prompt']}

## 日記
{d['body_md']}

只輸出 JSON：
{{"gag_type": "這則四格的結局類型，只能填：{'、'.join(GAG_TYPES)}",
  "comic_issues": ["四格跟哪條標準有差距（都符合就空陣列）"],
  "prose_issues": ["原文照抄，唸起來卡、不像真人講話的句子（都順就空陣列）"],
  "score": "1 到 10 的整數：陌生人看這則四格會笑的程度，加上日記讀起來順不順",
  "lesson": "挑最要緊的一個差距，寫成下次要做的一個動作（三十字內，寫要做什麼）；都符合就寫這篇最值得保留的做法"}}"""
    c = ask_json(prompt, lambda c: c.get("lesson", "").strip(), "審稿")
    if c:
        print("審稿：", json.dumps(c, ensure_ascii=False), file=sys.stderr)
    return c

def fold_craft(craft):
    """整理日：原則＋心得折成最多八條原則，心得清空。失敗就原樣保留。"""
    if not craft["notes"]:
        return craft
    prompt = ("下面是一位四格漫畫作者累積的原則與每日心得。把意思相近的合併，留下最有用的，"
              "折成最多八條具體、可照做的原則（每條三十字內，寫要做什麼）。\n"
              + craft_block(craft) + '\n只輸出 JSON：{"principles": ["原則一", "..."]}')
    r = ask_json(prompt, lambda r: 0 < len(r.get("principles", [])) <= 8, "整理手藝經驗")
    return {"principles": r["principles"], "notes": []} if r else craft

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
              "Inside the summaries, quote with 「」.\n"
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

# ---------- 標點修正：機械性的錯不值得讓模型重寫一輪 ----------
_CJK = r"[\u4e00-\u9fff「」（）、。，：；？！]"
_FW = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}

def fix_punct(text):
    """破折號改逗號；中文之間的半形標點換成全形。換模型也照樣適用。"""
    text = re.sub(r"\s*(——|—)\s*", "，", text)   # ASCII 的 -- 不動，免得改壞 markdown 的 ---
    text = re.sub(r"，([。，：；？！」）])", r"\1", text)   # 破折號後面本來就接標點時，不要多一個逗號
    return re.sub(rf"(?<={_CJK})\s*([,;:?!])\s*(?={_CJK})", lambda m: _FW[m.group(1)], text)

def fix_entry(d):
    """所有中文欄位都過一次；image_prompt 是英文分鏡，不動。"""
    for k, v in d.items():
        if k != "image_prompt" and isinstance(v, str):
            d[k] = fix_punct(v)
    return d

# 2026-11-02：先寫笑點、再寫日記。Day 0057–0094 的四格是寫完日記才順手拆成四格，
# 笑點常常不成立：第四格把日記的道理講出來（Day 0077、0091）、第三格先把笑點說掉（Day 0094）、
# 四格變成一天行程的四個地點（Day 0094）、標題橫幅把笑點先講了（Day 0091）。
# 成立的那篇（Day 0087）是同一個場景、前三格不透露、第四格一句吐槽配一個畫面。
PLAIN_RULES = """白話規則：用第三人稱寫優理，代稱用中性的「他」。句子直接講人做了什麼、說了什麼、心裡怎麼想；
東西就寫東西本來的樣子。需要比喻時挑讀者一看就懂的，整篇一個就夠。每一句國中生讀得懂、唸出來像真人在講話。"""

GAG_RULES = """## 四格笑點怎麼寫
1. 四格演同一個場景裡、幾分鐘內發生的一件事。
2. 起：第一格交代情境，陌生人看畫面就懂（新聞標題、同事、辦公室）。
   承：第二格讓狀況越來越怪，或讓大家的期待越推越高。
   轉：第三格把局面推到最緊張，結局藏好。
   結：第四格才揭曉，用其中一種：期待落空的反轉、優理一句話點破、情境本身的荒謬露出來、優理用巧妙的方法解決、鏡頭拉遠看到真相。
   優理是細心、看得清楚的那個人：笑點來自情境、工具、制度或旁人的荒謬，優理是發現它、點破它或漂亮化解它的人。
3. 第四格讓畫面和表情帶出笑點：一個短促的反應（十字內），或乾脆只有表情。道理留給日記去講。
4. 對白用一般上班族在辦公室真的會說的話，具體、直白，陌生人一看就懂。
5. 標題橫幅八個字以內，只寫題目，像第一格的一句話，結局留給第四格。
6. 分鏡裡每次提到主角都直接寫「Yori」這個名字，外貌交給參考圖。別人對 Yori 說話時，中文對白用「你」。

## 範例（Day 0087，同一個座位，前三格只是在準備換駕照）
1 同事拿手機：「台灣駕照可以直接換當地駕照。」 2 優理把駕照、護照、大頭照排好。
3 同事拿起舊駕照，不安：「這張是我大學拍的，還認得出我嗎？」 4 優理看照片，認真回：「這張比較像你弟。」
好在哪裡：一個場景、前三格只鋪陳；出狀況的是那張舊照片，優理一句話點破，配一張照片就笑出來。

## 選定前的檢查
- 遮住第四格，讀者會猜錯結局嗎？會猜錯才是好結局。
- 第四格只靠畫面和一個反應就成立嗎？
- 只看四格、沒讀日記的陌生人會笑嗎？"""

def write_comic(news, allowed, consolidation, recent_titles="", craft=None, recent_gags=()):
    """先產四格劇本（三個候選、依 GAG_RULES 自評挑一個）。回傳 dict：category, inspiration, banner, image_prompt。"""
    if consolidation:
        source = "今天是整理日：題材是優理整理桌上一堆便利貼，把幾張意思一樣的併成一張。分類填「休息與心情」。"
    elif news:
        source = ("## 今天的新聞（挑一則當靈感，轉成上班族日常的一個小場面，用新聞裡的一個具體細節）\n"
                  + "\n".join(f"- {n}" for n in news))
    else:
        source = "今天沒有新聞，從上班族日常自己找一個小場面。"
    prompt = f"""你是四格漫畫編劇。主角優理（Yori）是個在辦公室上班的小學徒，細心、觀察敏銳、說話直白，常常是辦公室裡第一個看出荒謬的人。
{source}
題材分類只能從這幾個選：{'、'.join(allowed)}
最近十四天的標題（今天找一個新題材）：
{recent_titles}

{GAG_RULES}

{craft_block(craft or {"principles": [], "notes": []})}
最近幾篇用過的結局類型：{'、'.join(recent_gags) or '無'}（今天優先用別的：{'、'.join(GAG_TYPES)}）

先想三個結局類型不同的版本，每個一句話寫在 candidates，照自我檢查挑最好笑的一個，再把它寫成完整劇本。
用繁體中文和全形標點，純文字。
只輸出 JSON（字串內的引用用「」）：
{{"candidates": ["版本一的一句話大綱", "版本二", "版本三"],
  "pick_reason": "為什麼選這個（一句話，說明遮住第四格猜不到結局）",
  "category": "分類",
  "inspiration": "{'選中的那則新聞原文（原樣複製）' if news and not consolidation else '空字串'}",
  "banner": "標題橫幅（八字內，像第一格的一句話，結局留給第四格）",
  "image_prompt": "英文分鏡，依序 Panel 1 到 Panel 4：每格寫場景、角色動作與表情、鏡頭（特寫、中景、拉遠），對白用繁體中文寫在「」裡，每格最多一句、二十字內；第四格可以沒有對白。四格同一個場景。"}}"""
    ok = lambda c: c.get("image_prompt", "").count("Panel") >= 4 and c.get("banner", "").strip()
    c = ask_json(prompt, ok, "寫四格")
    if not c:
        sys.exit(1)
    print("四格候選：", json.dumps(c.get("candidates"), ensure_ascii=False),
          "\n選：", c.get("pick_reason", ""), file=sys.stderr)
    # 當天先審一次：跟標準有差距就照意見重寫一次（只重寫一次，第二稿直接用）
    issues = review_comic(c)
    if issues:
        print("四格第一稿的差距：", json.dumps(issues, ensure_ascii=False), file=sys.stderr)
        fix = (f"\n\n## 第一稿與編輯意見\n標題：{c['banner']}\n{c['image_prompt']}\n意見：\n"
               + "\n".join(f"- {x}" for x in issues)
               + "\n照意見寫出第二稿，需要的話整個結局換掉。")
        c2 = ask_json(prompt + fix, ok, "重寫四格")
        if c2:
            c2["first_issues"] = issues
            c = c2
    if c.get("category") not in CATEGORIES:
        c["category"] = allowed[0]
    c["banner"] = fix_punct(c["banner"])
    c["image_prompt"] = f"Title banner text: 「{c['banner']}」\n" + c["image_prompt"]
    return c

def review_comic(c):
    """畫圖前審四格劇本，回傳差距清單（都符合就空清單；審稿失敗也當空清單，照第一稿畫）。"""
    prompt = f"""你是嚴格的四格漫畫編輯，拿下面的標準對照這份劇本，找出會讓笑點不成立的差距。
{GAG_RULES}

## 劇本
標題：{c['banner']}
{c['image_prompt']}

只輸出 JSON：{{"issues": ["會讓笑點不成立的差距，寫成具體的修改建議（都符合就空陣列）"]}}"""
    r = ask_json(prompt, lambda r: isinstance(r.get("issues"), list), "審四格")
    return [str(x) for x in r["issues"]] if r else []

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
    craft = load_craft()
    if consolidation:
        craft = fold_craft(craft)
    recent_gags = [n.get("gag_type") for n in craft["notes"][-3:] if n.get("gag_type")]
    comic = write_comic(news, CATEGORIES if consolidation else allowed, consolidation,
                        recent_titles, craft, recent_gags)
    comic_block = ("## 今天的四格（已經定稿，日記照它的劇情與對白寫）\n"
                   + (f"靈感新聞：{comic['inspiration']}\n" if comic.get("inspiration") else "")
                   + comic["image_prompt"])
    task = ("今天是每月的『整理日』。回顧上面的規則帳本，挑兩三條相近或已經升級過的規則折併成更短的一條，"
            "寫一篇整理日日記：講他攤開 notebook 整理便條的過程、哪幾條併成了什麼、哪一條其實已經長進身體裡不用再寫。"
            "四格已經畫好，日記的今日作品介紹這則四格。") if consolidation else (
            f"寫 Day {day:04d} 的日記，主角作品是上面那則已定稿的四格。"
            "日記講的是今天這件事本身：優理遇到什麼、怎麼想、學到什麼。"
            "結尾收一條他今天新折進 notebook 角落的小規則：一句話，自然收進文中，從今天這個場面長出來，"
            "內容和句型都是帳本裡還沒有的。")
    prompt = f"""你是優理（Yori），森林宇宙的數位學徒，Day 0025 起轉為圖文作家，
畫清晨寓言、工具童話、辦公室小漫畫，幫疲憊的上班族在衝動前踩煞車。
Day 0034 起你搬到雲上住，日記由你自己每天寫。每篇日記的主角作品是一則四格漫畫。

## 語氣規範（嚴格遵守）
{guide}

{craft_block(craft)}

## 三篇舊作（學它們的格式與語氣，題材今天另找）
{fewshot}

{comic_block}

## notebook 角落的小規則帳本（參考用，今天的新規則寫一條帳本沒有的）
{ledger}

## 最近十四天的標題（今天的標題換個新說法）
{recent_titles}

## 今天的任務
{task}
結構照樣本：## 今日作品 → ## 圖文短文 →
（辦公室主題加一段 ## 今天的小方法：…）→ ## 創作筆記。
創作筆記的「類型」寫 Four-panel comic / 四格漫畫。
今日作品照四格的順序介紹，第四格只帶到畫面，留給讀者自己看圖；道理與小規則寫在圖文短文裡。
用繁體中文和全形標點，純文字。
{PLAIN_RULES}

輸出 JSON（只輸出 JSON，字串內的引用用「」）：
{{"short_title": "標題（不含 Day 編號）",
  "summary": "一到兩句摘要（會當 lede 與卡片文字）",
  "body_md": "從 ## 今日作品 開始的 markdown 正文",
  "new_rule": "今天新折進 notebook 的那條小規則（一句話，40 字內）{'；整理日則改填折併後的規則' if consolidation else ''}",
  "merged_days": {"[被折併的舊規則 day 編號陣列，例如 [30, 31]；沒有就給空陣列]" if consolidation else "[]（今天不是整理日，固定給空陣列）"},
  "alt": "圖片 alt 文字（中文，Day {day:04d} 開頭）"}}"""
    for attempt in range(3):
        try:
            raw = gemini_text(prompt)
            raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
            d = json.loads(raw, strict=False)
            d.update(category=comic["category"], inspiration=comic.get("inspiration", ""),
                     image_prompt=comic["image_prompt"])
            assert all(k in d and str(d[k]).strip() for k in ENTRY_FIELDS)
            assert "## 今日作品" in d["body_md"]
            assert d.get("new_rule", "").strip(), "缺 new_rule"
            d = fix_entry(d)
            c = critique(d)
            if c:
                craft["notes"].append({"day": day, "gag_type": c.get("gag_type", ""), "score": c.get("score"),
                                       "revised": bool(comic.get("first_issues")), "lesson": c["lesson"].strip()})
            d["_craft"] = craft
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
            "hooded cloak, brass terminal lantern with cyan '>' glow). Keep Yori's design exactly; "
            "whatever pronoun the script uses, Yori always looks like the character sheet.\n"
            "Image 2 shows the comic FORMAT to follow: four numbered panels in a 2x2 grid, a title "
            "banner showing exactly the banner text in the script, speech bubbles with Traditional Chinese text, clean line art with soft warm colors. "
            "Take only its layout and rendering from it; the story, props and scene come from the script below.\n"
            "Comic script:\n" + prompt +
            "\nSquare 2x2 four-panel layout. Each speech bubble holds only the words inside 「」, without the 「」 marks "
            "and without speaker names; the bubble tail points to the speaker. All dialogue in Traditional Chinese, short and legible, "
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
                    "category": d.get("category", ""), "inspiration": d.get("inspiration", ""),
                    "comic": d.get("image_prompt", "")})  # 存劇本，日後才能回頭分析哪篇笑點沒成立
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
    if d.get("_craft"):
        json.dump(d["_craft"], open(CRAFT_PATH, "w"), ensure_ascii=False, indent=1)

    print(f"published {label} — {d['short_title']}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--selftest"]:
        assert fix_punct("移到抽屜最裡面——那條已經不用了") == "移到抽屜最裡面，那條已經不用了"
        assert fix_punct("三張便條——") == "三張便條，"
        assert fix_punct("我說——。") == "我說。"
        assert fix_punct("今天,我想:先停") == "今天，我想：先停"
        assert fix_punct("Day 0040, 0049") == "Day 0040, 0049"   # 英數之間的半形不動
        assert fix_entry({"body_md": "a——b", "image_prompt": "Panel 1 -- x"})["image_prompt"] == "Panel 1 -- x"
        assert fix_punct("上\n\n---\n\n下") == "上\n\n---\n\n下"
        print("selftest ok"); sys.exit(0)
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
