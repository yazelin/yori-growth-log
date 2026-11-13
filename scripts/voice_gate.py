#!/usr/bin/env python3
"""優理日記的語氣閘門：擋住讀起來像語言模型寫的稿。

兩關，任何一關沒過就退稿：
  1. 程式檢查（check_rules）：句型黑名單、口頭禪額度、結尾和前幾天太像。規則在 voice_rules.json。
  2. 對抗審稿（review）：換一家模型專門挑像模型寫的句子，要逐句照抄原文。
     審稿人連不上、回傳格式壞掉、照抄的句子對不上原文，一律算沒過（寧可不發）。

本機用法：
  python3 scripts/voice_gate.py --day 104            檢查已發的某一篇（拿它之前的幾篇當歷史）
  python3 scripts/voice_gate.py --day 104 --rules-only   只跑程式檢查，不花模型
  python3 scripts/voice_gate.py --text 稿.txt        檢查一段還沒發的文字（歷史用全部已發的）
  python3 scripts/voice_gate.py --calibrate 95,104 --pass 98,102   量審稿人：前者該退、後者該過
  python3 scripts/voice_gate.py --selftest

審稿人：llmshare 的 deepseek-v4.1-flash:1017（金鑰 LLMSHARE_API_KEY）。llmshare 只准用這一個模型，換別的要先問作者。
"""
import json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(ROOT, "scripts", "voice_rules.json")
LLM_BASE = "https://llm-share.duotify.com/v1"
GEMINI_WEB_BASE = os.environ.get("GEMINI_WEB_BASE_URL", "https://ching-tech.ddns.net/gemini-web").rstrip("/")
LLMSHARE_MODEL = "deepseek-v4.1-flash:1017"   # llmshare 只准用這一個
FLAG_TYPES = ["否定鋪墊", "道理收尾", "重述畫面", "排比對仗", "書面腔", "宣告成長", "空話", "其他"]

REVIEW_PROMPT = """你是出版社的資深繁體中文編輯，工作是分辨一段稿子是真人寫的，還是語言模型寫的。
下面這段短文是一個角色的日記，會在視覺小說裡一句一句念給讀者聽。請逐句讀，把讀起來像語言模型寫的句子挑出來。

語言模型寫的句子常有這些跡象：
- 否定鋪墊：先講主角「沒有」做某件沒人提過的事，或用「不是……而是……」，再講正題。
- 道理收尾：段落或全文最後收成一句道理、守則、心得。
- 重述畫面：前面已經演過的事，後面再用抽象的話解釋一遍它代表什麼。
- 排比對仗：三連項、前後兩句對得很工整、「先……再……」式的口訣。
- 書面腔：文藝比喻，或唸出聲來不像人在講話的句子。
- 宣告成長：直接寫主角「學到」「發現」「提醒自己」什麼。

真人寫的日記通常只講發生的事和當下的反應，句子長短不齊，讀完整段也不一定有結論。

只挑你有把握的句子。每一句從原文一字不差照抄（含標點），從下面的類型選一個：{types}

短文：
{text}

只輸出 JSON：
{{"flags": [{{"quote": "原文照抄的一句", "type": "類型", "why": "十五字內的理由"}}],
  "human_score": 1 到 10 的整數（10 是確定真人寫的）}}"""


REVIEW_PROMPT_METHOD = """你是出版社的資深繁體中文編輯，工作是分辨一段稿子是真人寫的，還是語言模型寫的。
下面這段是日記後面附的「小方法」，用幾個步驟教讀者一個做法。請逐句讀，把讀起來像語言模型寫的句子挑出來。

語言模型寫的小方法常有這些跡象：
- 否定鋪墊：先叫讀者「別急著」「不要只」做某件事，或用「不是……而是……」，再講做法。
- 道理收尾：步驟講完以後，多一句工整的話總結道理。
- 排比對仗：每一條都套同一個句型，或湊成整齊的口訣。
- 空話：聽起來有道理，照著做卻不知道手要動哪裡。
- 書面腔：唸出聲來不像人在教朋友做事。

真人寫的生活小技巧通常直接講手要做什麼、用到哪樣物品，每條長短不齊，講完就停。

只挑你有把握的句子。每一句從原文一字不差照抄（含標點），從下面的類型選一個：{types}

小方法：
{text}

只輸出 JSON：
{{"flags": [{{"quote": "原文照抄的一句", "type": "類型", "why": "十五字內的理由"}}],
  "human_score": 1 到 10 的整數（10 是確定真人寫的）}}"""


def load_rules():
    return json.load(open(RULES_PATH, encoding="utf-8"))


def prose_of(md):
    """取 ## 圖文短文 那一段（Larch 逐句念的就是這段）；沒有這個標題就整篇都看。"""
    m = re.search(r"^## 圖文短文\s*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return (m.group(1) if m else md).strip()


def method_of(md):
    """取 ## 今天的小方法 那一段，連標題那一行（標題也會套公式）；沒有這一段回空字串。"""
    m = re.search(r"^## (今天的小方法[^\n]*)\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return (m.group(1).strip() + "\n" + m.group(2).strip()) if m else ""


def closing_of(text):
    sents = [s for s in re.split(r"(?<=[。！？])", text.replace("\n", "")) if s.strip()]
    return sents[-1].strip() if sents else ""


def _bigrams(s):
    s = re.sub(r"[\s，。：；、！？「」『』（）]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similarity(a, b):
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def check_rules(text, history, rules):
    """history：之前幾篇的同一段文字，舊到新。回傳問題清單，空的代表過關。"""
    issues = []
    n, lim = len(_squash(text)), rules.get("length")
    if lim and not lim["min"] <= n <= lim["max"]:
        issues.append({"rule": "長度", "quote": f"{n} 字",
                       "why": f"圖文短文要 {lim['min']} 到 {lim['max']} 字"})
    for p in rules["patterns"]:
        for m in re.finditer(p["regex"], text):
            issues.append({"rule": p["id"], "quote": m.group(0), "why": p["why"]})
    for q in rules["quota"]:
        if q["phrase"] in text:
            used = sum(q["phrase"] in h for h in history[-(q["window"] - 1):])
            if used + 1 > q["max"]:
                issues.append({"rule": "口頭禪", "quote": q["phrase"],
                               "why": f"最近 {q['window']} 篇已經用過 {used} 次，今天換個說法"})
    c = rules["closing"]
    end = closing_of(text)
    for h in history[-c["window"]:]:
        s = similarity(end, closing_of(h))
        if s >= c["max_similarity"]:
            issues.append({"rule": "結尾重複", "quote": end,
                           "why": f"和前幾天的結尾「{closing_of(h)}」太像（{s:.2f}）"})
            break
    return issues


def check_method(text, history, rules):
    """小方法那一段的程式檢查。history：之前幾篇的小方法，舊到新。"""
    m, issues = rules["method"], []
    for p in rules["patterns"][:2] + m["patterns"]:          # 對比句兩條通用，其餘是這一段專用
        for hit in re.finditer(p["regex"], text):
            issues.append({"rule": p["id"], "quote": hit.group(0), "why": p["why"]})
    for q in m["quota"]:
        if q["phrase"] in text:
            used = sum(q["phrase"] in h for h in history[-(q["window"] - 1):])
            if used + 1 > q["max"]:
                issues.append({"rule": "口頭禪", "quote": q["phrase"],
                               "why": f"最近 {q['window']} 篇的小方法已經用過 {used} 次，今天換個說法"})
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if m.get("end_on_step") and len(lines) > 1 and any(l.startswith("- ") for l in lines) \
            and not lines[-1].startswith("- "):
        issues.append({"rule": "道理收尾", "quote": lines[-1], "why": "步驟講完就停，最後這句總結拿掉"})
    return issues


def _llmshare(prompt):
    body = {"model": LLMSHARE_MODEL, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(LLM_BASE + "/chat/completions", json.dumps(body).encode(),
        {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLMSHARE_API_KEY"]})
    return json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]


def _gemini_web(prompt):
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}
    req = urllib.request.Request(f"{GEMINI_WEB_BASE}/v1beta/models/gemini-2.5-flash:generateContent",
        json.dumps(body).encode(),
        {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    d = json.load(urllib.request.urlopen(req, timeout=300))
    return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])


def reviewer_name(who=None):
    return "gemini-web" if who == "gemini-web" else LLMSHARE_MODEL


def ask_reviewer(prompt, who=None):
    """預設 deepseek。2026-11-13 拿六段真人散文和六篇舊稿量過：deepseek 分得開（真人最多點 2 句、
    舊稿多在 3 句以上），gemini-web 分不開（真人六段會退三段），所以 gemini-web 只在指名時用。"""
    return _gemini_web(prompt) if who == "gemini-web" else _llmshare(prompt)


def _squash(s):
    return re.sub(r"\s+", "", s)


def parse_review(raw, text):
    """回傳 (flags, human_score)。格式不對就丟例外，由呼叫端當成沒過。"""
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    m = re.search(r"\{.*\}", raw, re.S)
    d = json.loads(m.group(0) if m else raw, strict=False)
    if not isinstance(d.get("flags"), list):
        raise ValueError("審稿回傳缺 flags")
    body = _squash(text)
    flags, made_up = [], 0
    for f in d["flags"]:
        q = str(f.get("quote", "")).strip()
        if len(_squash(q)) >= 4 and _squash(q) in body:
            flags.append({"quote": q, "type": f.get("type") if f.get("type") in FLAG_TYPES else "其他",
                          "why": str(f.get("why", "")).strip()})
        else:
            made_up += 1
    if made_up and made_up >= max(1, len(d["flags"]) // 2):
        raise ValueError(f"審稿人照抄的 {len(d['flags'])} 句裡有 {made_up} 句對不上原文")
    return flags, int(d.get("human_score") or 0)


def review(text, tries=2, who=None, prompt_tpl=None):
    """回傳 {"ok": bool, "flags": [...], "human_score": n, "error": str|None}。審不出來算沒過。"""
    prompt = (prompt_tpl or REVIEW_PROMPT).format(types="、".join(FLAG_TYPES), text=text)
    err = None
    for attempt in range(tries):
        try:
            flags, score = parse_review(ask_reviewer(prompt, who), text)
            return {"flags": flags, "human_score": score, "error": None}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"審稿第 {attempt + 1} 次失敗：{err}", file=sys.stderr)
            time.sleep(5)
    return {"flags": [], "human_score": 0, "error": err}


def gate(text, history, rules=None, rules_only=False):
    """整道閘門。回傳 {"ok", "rule_issues", "review"}。"""
    rules = rules or load_rules()
    rule_issues = check_rules(text, history, rules)
    out = {"ok": not rule_issues, "rule_issues": rule_issues, "review": None}
    if rule_issues or rules_only:      # 程式檢查沒過就不花模型
        return out
    r = review(text)
    out["review"] = r
    out["ok"] = r["error"] is None and len(r["flags"]) <= rules["review"]["max_flags"]
    return out


def gate_entry(md, history_mds, rules=None, rules_only=False, summary=None):
    """整篇的閘門：圖文短文和小方法各自過程式檢查與審稿。history_mds：之前幾篇的 markdown，舊到新。"""
    rules = rules or load_rules()
    res = gate(prose_of(md), [prose_of(h) for h in history_mds], rules, rules_only)
    res["method_issues"], res["method_review"] = [], None
    if summary:      # 摘要會當首頁卡片文字：句型黑名單照查，另外不提小規則
        for p in rules["patterns"]:
            for hit in re.finditer(p["regex"], summary):
                res["rule_issues"].append({"rule": "摘要／" + p["id"], "quote": hit.group(0), "why": p["why"]})
        for w in rules.get("summary_banned", []):
            if w in summary:
                res["rule_issues"].append({"rule": "摘要", "quote": w, "why": "摘要只講今天這個場面"})
        res["ok"] = res["ok"] and not res["rule_issues"]
    text = method_of(md)
    if text and rules.get("method") and not rules["method"].get("allowed", True):
        res["method_issues"] = [{"rule": "不寫小方法", "quote": text.split("\n")[0],
                                 "why": "日記只有今日作品、圖文短文、創作筆記三段，這一段整段拿掉"}]
        res["ok"] = False
    elif text and rules.get("method"):
        res["method_issues"] = check_method(text, [method_of(h) for h in history_mds], rules)
        mr = rules["method"].get("review") or {}
        ok = not res["method_issues"]
        if ok and res["ok"] and not rules_only and mr.get("enabled"):
            r = review(text, prompt_tpl=REVIEW_PROMPT_METHOD)
            res["method_review"] = r
            ok = r["error"] is None and len(r["flags"]) <= mr["max_flags"]
        res["ok"] = res["ok"] and ok
    return res


def feedback(result):
    """把沒過的原因寫成給寫手看的重寫意見。"""
    lines = [f"- 圖文短文「{i['quote']}」：{i['why']}" for i in result["rule_issues"]]
    r = result.get("review")
    if r and r["flags"]:
        lines += [f"- 圖文短文「{f['quote']}」：{f['type']}，{f['why']}" for f in r["flags"]]
    lines += [f"- 小方法「{i['quote']}」：{i['why']}" for i in result.get("method_issues") or []]
    r = result.get("method_review")
    if r and r["flags"]:
        lines += [f"- 小方法「{f['quote']}」：{f['type']}，{f['why']}" for f in r["flags"]]
    return "\n".join(lines)


def record(result, day, rules=None):
    """把審稿人點名的句型記進帳本；同一個四字以上的片段在兩天被點名，就自動進口頭禪額度。"""
    rules = rules or load_rules()
    flags = [f for k in ("review", "method_review") for f in ((result.get(k) or {}).get("flags") or [])]
    if not flags:
        return rules
    quotes = [f["quote"] for f in flags]
    known = {q["phrase"] for q in rules["quota"]}
    for old in rules["ledger"]:
        if old["day"] == day:
            continue
        for a in quotes:
            for b in old["quotes"]:
                frag = common_fragment(a, b)
                if frag and frag not in known:
                    rules["quota"].append({"phrase": frag, "window": 7, "max": 1,
                                           "from": [old["day"], day]})
                    known.add(frag)
    rules["ledger"] = [e for e in rules["ledger"] if e["day"] != day][-60:] + [
        {"day": day, "quotes": quotes, "types": [f["type"] for f in flags]}]
    json.dump(rules, open(RULES_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rules


def common_fragment(a, b, min_len=4):
    """兩句共有的最長連續片段（不含標點），短於 min_len 就當沒有。"""
    best = ""
    for i in range(len(a)):
        for j in range(i + min_len, len(a) + 1):
            frag = a[i:j]
            if re.search(r"[，。：；、！？「」\s]", frag):
                break
            if frag in b and len(frag) > len(best):
                best = frag
    return best


def _entries():
    return json.load(open(os.path.join(ROOT, "docs", "entries.json"), encoding="utf-8"))


def _prose_by_day():
    out = {}
    for e in _entries():
        p = os.path.join(ROOT, e.get("entry_markdown") or "")
        if e.get("entry_markdown") and os.path.exists(p):
            out[e["day"]] = prose_of(open(p, encoding="utf-8").read())
    return out


def _show(label, res):
    print(f"{label}：{'過關' if res['ok'] else '退稿'}")
    for i in res["rule_issues"]:
        print(f"  [程式] {i['rule']}　「{i['quote']}」　{i['why']}")
    for i in res.get("method_issues") or []:
        print(f"  [程式／小方法] {i['rule']}　「{i['quote']}」　{i['why']}")
    for r in (res.get("review"), res.get("method_review")):
        if not r:
            continue
        if r["error"]:
            print(f"  [審稿] 審不出來，算沒過：{r['error']}")
        else:
            print(f"  [審稿] 點名 {len(r['flags'])} 句，像真人 {r['human_score']}/10")
            for f in r["flags"]:
                print(f"    {f['type']}　「{f['quote']}」　{f['why']}")


def _selftest():
    rules = {**load_rules(), "length": None}
    bad = "優理沒有說鍵盤墊不好。他今天學到，安靜不是一件事，而是很多件事。"
    got = {i["rule"] for i in check_rules(bad, [], rules)}
    assert {"否定鋪墊", "宣告成長", "不是而是"} <= got, got
    good = "同事把洋芋片撕開，整層樓都聽到了。我看了一眼分貝計，沒講話。"
    assert not check_rules(good, [], rules), check_rules(good, [], rules)
    assert not check_rules("沒有人去看杯身。", [], rules)           # 一般的「沒有」不該被擋
    hist = ["他把規則折進 notebook 角落：先看發車時間。"]
    assert any(i["rule"] == "口頭禪" for i in check_rules("今天也收進 notebook 角落。", hist, rules))
    assert not any(i["rule"] == "口頭禪" for i in check_rules("今天也收進 notebook 角落。", [], rules))
    same = "他把規則寫下來：先看機器現在在做什麼，再決定要開還是要關。"
    assert any(i["rule"] == "結尾重複" for i in check_rules(same, [same], rules))
    flags, _ = parse_review('{"flags":[{"quote":"優理沒有說鍵盤墊不好。","type":"否定鋪墊","why":"x"}],"human_score":3}', bad)
    assert len(flags) == 1
    try:
        parse_review('{"flags":[{"quote":"這句原文裡根本沒有。","type":"其他","why":"x"}]}', bad)
        raise AssertionError("對不上原文的照抄應該丟例外")
    except ValueError:
        pass
    try:
        parse_review("抱歉，我無法處理", bad)
        raise AssertionError("壞格式應該丟例外")
    except ValueError:
        pass
    assert common_fragment("他把一張小紙條折進去", "又是一張小紙條") == "一張小紙條"
    assert common_fragment("今天很好", "明天很壞") == ""
    md = "## 圖文短文\n" + "字" * 300 + "\n\n## 今天的小方法：遙控器三秒檢查法\n先別急著按。\n\n- 看螢幕。\n- 再按。\n\n先看清楚，才不會白忙。\n\n## 創作筆記\n- x"
    got = {i["rule"] for i in check_method(method_of(md), [], rules)}
    assert {"別急著", "才不會", "道理收尾"} <= got, got
    assert any(i["rule"] == "口頭禪" for i in check_method(method_of(md), ["今天的小方法：抽屜檢查法\n- a"], rules))
    clean = "今天的小方法：找句號從哪來\n- 看輸入框裡有沒有句號。\n- 打開公司公告那一頁。"
    assert not check_method(clean, [], rules), check_method(clean, [], rules)
    assert method_of("## 圖文短文\n沒有小方法") == ""
    assert not gate_entry(md, [], rules, rules_only=True)["ok"]
    bad_sum = gate_entry("## 圖文短文\n好。", [], rules, rules_only=True, summary="今天的小規則是先看再按。")
    assert any(i["rule"] == "摘要" for i in bad_sum["rule_issues"]) and not bad_sum["ok"]
    assert gate_entry("## 圖文短文\n好。", [], rules, rules_only=True, summary="同事炫耀新掛燈。")["ok"]
    off = {**rules, "method": {**rules["method"], "allowed": False}}
    assert [i["rule"] for i in gate_entry("## 圖文短文\n好。\n\n## 今天的小方法：x\n- a", [], off, rules_only=True)["method_issues"]] == ["不寫小方法"]
    assert gate_entry("## 圖文短文\n好。\n\n## 創作筆記\n- a", [], off, rules_only=True)["ok"]
    full = load_rules()
    assert any(i["rule"] == "長度" for i in check_rules("太短了。", [], full))
    assert not any(i["rule"] == "長度" for i in check_rules("字" * 300, [], full))
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]:
        _selftest(); sys.exit(0)
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    prose = _prose_by_day()
    days = sorted(prose)
    hist_before = lambda d: [prose[x] for x in days if x < d]
    if "--calibrate" in a:
        rules = load_rules()
        want = [(int(d), False) for d in opt("--calibrate").split(",")] + \
               [(int(d), True) for d in (opt("--pass") or "").split(",") if d]
        right = 0
        for d, should_pass in want:
            r = review(prose[d])
            ok = r["error"] is None and len(r["flags"]) <= rules["review"]["max_flags"]
            right += ok == should_pass
            print(f"Day {d:04d}　該{'過' if should_pass else '退'}　實際{'過' if ok else '退'}　"
                  f"點名 {len(r['flags'])} 句　像真人 {r['human_score']}/10　{r['error'] or ''}")
        print(f"{reviewer_name()}：{right}/{len(want)} 判對")
        sys.exit(0)
    if "--text" in a:
        text, hist, label = open(opt("--text"), encoding="utf-8").read().strip(), [prose[x] for x in days], "這段文字"
    else:
        d = int(opt("--day"))
        text, hist, label = prose[d], hist_before(d), f"Day {d:04d}"
    if "--text" in a:
        res = gate(text, hist, rules_only="--rules-only" in a)
    else:
        mds = {e["day"]: open(os.path.join(ROOT, e["entry_markdown"]), encoding="utf-8").read()
               for e in _entries() if e.get("entry_markdown")}
        res = gate_entry(mds[d], [mds[x] for x in sorted(mds) if x < d], rules_only="--rules-only" in a)
    _show(label, res)
    sys.exit(0 if res["ok"] else 1)
