"""每句配表情與畫面：句子照規則切好，模型看著四格圖替每句挑「對到第幾格」和優理的表情，不動文字。
結果快取在 larch/faces/<key>.json，句子或可選的表情改了才重挑。"""
import base64, io, json, os, re, sys, urllib.request
from PIL import Image

# 日常會用到的表情與動作。只放平常說話時的臉，誇張的表情不給模型選。
FACES = {"plain": "平常、在敘述事情", "smile": "淡淡的微笑", "happy": "開心地笑", "smallsurprise": "有點意外",
         "puzzled": "疑惑、想不通", "thinking": "想事情", "worried": "有點擔心", "tired": "有點累、無奈",
         "shy": "不好意思", "relieved": "鬆一口氣", "wry": "尷尬地笑、自嘲",
         "draw": "（動作）拿筆在本子上畫或寫", "phone": "（動作）看手機、讀訊息", "mug": "（動作）捧著杯子喝東西",
         "hug": "（動作）抱著畫冊，安心滿足"}
MODEL = "deepseek-v4.1-flash:1017"
PROMPT = """這是優理的四格漫畫，下面是同一天的日記旁白，已經切成 {n} 句。
替每一句挑兩件事：
1. panel：這句在講的是第幾格（1 到 4）。旁白提到的事情畫在哪一格就選哪一格。
   這句講的是四格裡沒有畫出來的事（事後的心得、小規則、明天的打算），就填 0，代表看整張四格。
2. face：這句念的時候，旁邊站著的優理是什麼表情或動作，只能從下面的代號選：
{faces}
大部分句子用 plain 或 smile。動作類（draw、phone、mug、hug）只在句子裡真的寫到那個動作時才用。
只輸出 JSON 陣列，長度剛好 {n}，例如 [{{"panel":1,"face":"plain"}}]。

{lines}"""


def _ask(prompt, image):
    buf = io.BytesIO()
    im = Image.open(image).convert("RGB")
    im.thumbnail((900, 900))
    im.save(buf, "JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    body = {"model": MODEL, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}]}
    req = urllib.request.Request(os.environ.get("LLMSHARE_BASE_URL", "https://llm-share.duotify.com/v1") + "/chat/completions",
                                 json.dumps(body).encode(), {"Content-Type": "application/json",
                                                             "Authorization": "Bearer " + os.environ["LLMSHARE_API_KEY"]})
    return json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]


def pick(key, texts, image, cache, ask=True):
    """回傳 [{"panel": 1-4, "face": 代號}]，長度跟 texts 一樣。失敗就全部 plain、照順序分格。"""
    path = cache / f"{key}.json"
    sig = {"texts": texts, "faces": sorted(FACES), "prompt": PROMPT}
    if path.exists():
        c = json.loads(path.read_text("utf-8"))
        if c.get("sig") == sig:
            return c["picks"]
    if not ask:  # 只讀快取：還沒挑過就先用一般、整張
        return [{"panel": None, "face": "plain"} for _ in texts]
    prompt = PROMPT.format(n=len(texts), faces="\n".join(f"- {k}：{v}" for k, v in FACES.items()),
                           lines="\n".join(f"{i+1}. {t}" for i, t in enumerate(texts)))
    for _ in range(2):
        try:
            out = _ask(prompt, image)
            picks = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
        except Exception as e:  # noqa: BLE001  網路、格式錯都重試一次
            print(key, "挑選失敗：", e, file=sys.stderr)
            continue
        if len(picks) == len(texts):
            picks = [{"panel": p.get("panel") if p.get("panel") in (0, 1, 2, 3, 4) else None,
                      "face": p.get("face") if p.get("face") in FACES else "plain"} for p in picks]
            cache.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"sig": sig, "picks": picks}, ensure_ascii=False), "utf-8")
            return picks
    return [{"panel": None, "face": "plain"} for _ in texts]
