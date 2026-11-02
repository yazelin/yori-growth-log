"""把一篇日記切成幾句、每句配一張立繪表情，結果快取在 larch/pages/。

切句只能切，不能改寫：各句串起來（去掉空白）必須等於原本的 body。
模型兩次都沒切對時，改用標點機械切句、表情一律 plain，而且不寫快取，
下一班會再請模型切一次。
"""
import hashlib
import json
import re

FACES = {
    "plain": "平常說話，沒有特別情緒",
    "crash": "當機、腦袋過載、算不出來、系統錯誤",
    "feature": "得意、叉腰比手指，「這不是 Bug，是 Feature」那種自豪",
    "happy": "開心、興奮、感動",
    "snack": "嘴饞、想吃東西、講到食物",
    "curious": "好奇、疑問、在想事情",
    "panic": "驚訝、慌張、嚇一跳",
    "sleepy": "想睡、累了、晚安",
    "lonely": "寂寞、失落、想念",
}
MAX_LINE = 60

PROMPT = """下面是一篇格莉奇的日記。請把它切成 3 到 8 句，讓她在視覺小說裡一句一句講，每句不超過 {max_line} 個字。
規則：只能切，不能改字、不能刪字、不能加字，標點也要保留；所有句子依序接起來要和原文一字不差（空白和換行可以省略）。
每句配一個表情，只能從下面挑：
{faces}

日記：
{body}

只輸出 JSON 陣列：[{{"text": "第一句", "face": "plain"}}, ...]"""


def _squash(s):
    return re.sub(r"\s+", "", s)


def post_key(posts):
    """給每篇一個 "<date>-<N>"，N 是同一天在 posts.json 出現的順序，從 1 起。"""
    seen = {}
    out = []
    for p in posts:
        seen[p["date"]] = seen.get(p["date"], 0) + 1
        out.append((f"{p['date']}-{seen[p['date']]}", p))
    return out


def _parse(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    m = re.search(r"\[.*\]", raw, re.S)
    data = json.loads(m.group(0) if m else raw)
    return [{"text": str(d["text"]).strip(),
             "face": d.get("face") if d.get("face") in FACES else "plain"}
            for d in data if str(d.get("text", "")).strip()]


def split_post(post, ask):
    """ask(prompt) -> str。切錯就重問一次，再錯丟 ValueError。"""
    faces = "\n".join(f"- {k}：{v}" for k, v in FACES.items())
    prompt = PROMPT.format(max_line=MAX_LINE, faces=faces, body=post["body"])
    for _ in range(2):
        try:
            lines = _parse(ask(prompt))
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if lines and _squash("".join(l["text"] for l in lines)) == _squash(post["body"]):
            return lines
    raise ValueError("模型切句和原文對不上")


def fallback_split(body):
    """依段落、句末標點切，同一段裡的句子盡量併到 MAX_LINE 字內。"""
    lines = []
    for para in re.split(r"\n\s*\n", body.strip()):
        para = para.strip()
        if not para:
            continue
        cur = ""
        sents = re.findall(r"[^。！？!?…]*[。！？!?…」』）)]+|[^。！？!?…]+$", para)
        if _squash("".join(sents)) != _squash(para):
            sents = [para]  # 切不乾淨就整段一句，寧可長也不能掉字
        for sent in sents:
            if cur and len(cur) + len(sent) > MAX_LINE:
                lines.append(cur)
                cur = ""
            cur += sent
        if cur:
            lines.append(cur)
    return [{"text": t, "face": "plain"} for t in lines]


def load_or_split(key, post, ask, cache_dir):
    sha = hashlib.sha1(post["body"].encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.exists():
        cached = json.loads(path.read_text("utf-8"))
        if cached.get("body_sha1") == sha:
            return cached["lines"]
    try:
        lines = split_post(post, ask)
    except ValueError as e:
        print(f"  {key}：{e}，這次先用標點切句", flush=True)
        return fallback_split(post["body"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"body_sha1": sha, "lines": lines}, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return lines
