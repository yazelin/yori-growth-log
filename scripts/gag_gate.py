#!/usr/bin/env python3
"""四格閘門：畫圖前先量「遮住第四格猜不猜得到結局」。

做法：只給審稿人前三格，請他猜第四格三種收尾；再給全篇，判斷真正的收尾有沒有被猜中，並打好笑分數。
評 RUNS 次，任何一次被猜中、或分數低於 MIN_FUNNY 就算沒過。

2026-11-13 量過（每則評三次，deepseek-v4.1-flash）：
  真人畫的四格十則（Peanuts 1965 年 1 月，逐格轉寫）：30 次裡被猜中 1 次，分數平均 6.2
  同十則故意弄壞（結局提前講掉、第四格平鋪直敘）：分數平均 4.2，十則裡七則掉到 3 分
  優理第 95 到 104 天的舊稿：30 次裡被猜中 22 次，分數平均 6.6
分數只分得出「弄壞的」，分不出真人和優理；猜中率才分得開，所以門檻以猜中為主。

審稿人出錯時回 None，呼叫端當成沒審、照常往下走（這道閘門不擋發佈）。

本機用法：
  python3 scripts/gag_gate.py --day 104          # 量某一天的舊稿
  python3 scripts/gag_gate.py --text script.txt  # 量一份分鏡
"""
import json, os, re, sys, time, urllib.request

LLM_BASE = "https://llm-share.duotify.com/v1"
MODEL = "deepseek-v4.1-flash:1017"   # llmshare 只用這一個模型
RUNS = 2
MIN_FUNNY = 5


def _ask(prompt, temp):
    body = {"model": MODEL, "temperature": temp, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(LLM_BASE + "/chat/completions", json.dumps(body).encode(),
        {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLMSHARE_API_KEY"]})
    raw = json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]
    return json.loads(raw[raw.index("{"):raw.rindex("}") + 1], strict=False)


def judge_once(script, ask=_ask):
    head = re.split(r"Panel\s*4\s*[:：]", script, maxsplit=1)[0]
    g = ask("下面是一則四格漫畫的前三格分鏡（第四格被遮住）。你是讀者，猜第四格最可能怎麼收尾，"
            "寫三個不同的猜測，每個一句話。\n\n" + head.strip() +
            '\n\n只輸出 JSON：{"guesses": ["猜測一", "猜測二", "猜測三"]}', 0.7)
    guesses = [str(x) for x in g["guesses"]]
    v = ask("你是四格漫畫編輯。下面是一則四格的完整分鏡，以及一位讀者只看前三格時對第四格的三個猜測。\n\n"
            "## 分鏡\n" + script.strip() + "\n\n## 讀者的猜測\n" + "\n".join(f"- {x}" for x in guesses) +
            "\n\n判斷兩件事：\n1. guessed：第四格真正的收尾，是否和任何一個猜測實質相同（同一個反轉、同一個揭露）。\n"
            "2. funny：沒看過這系列的陌生讀者，看完四格會笑的程度，1 到 10 的整數。"
            "1 是沒有笑點，3 是第四格只是把前面講過的再講一次或平鋪直敘，5 是看得懂哪裡想好笑但不會笑，"
            "7 是會微笑，9 是會笑出聲。\n"
            '只輸出 JSON：{"guessed": true 或 false, "hit": "被猜中的那個猜測原文（沒猜中就空字串）", '
            '"funny": 整數, "why": "一句話"}', 0)
    return {"guessed": bool(v["guessed"]), "hit": str(v.get("hit") or ""), "funny": int(v["funny"]),
            "why": str(v.get("why", "")), "guesses": guesses}


def judge(script, runs=RUNS, ask=_ask):
    """回 {"ok", "hits": 被猜中的猜測, "funny": 最低分, "why": [...], "runs": n}；審稿人全都出錯回 None。"""
    got = []
    for _ in range(runs):
        for attempt in range(2):
            try:
                got.append(judge_once(script, ask)); break
            except Exception as e:
                print(f"四格閘門審稿失敗：{e!r}"[:200], file=sys.stderr); time.sleep(8)
    if not got:
        return None
    hits = [r["hit"] or "（審稿人沒寫是哪一個）" for r in got if r["guessed"]]
    funny = min(r["funny"] for r in got)
    return {"ok": not hits and funny >= MIN_FUNNY, "hits": hits, "funny": funny,
            "why": [r["why"] for r in got], "runs": len(got)}


def feedback(v):
    lines = []
    if v["hits"]:
        lines.append("讀者只看前三格，就猜到第四格了：")
        lines += [f"- {h}" for h in v["hits"]]
    if v["funny"] < MIN_FUNNY:
        lines.append(f"編輯給的好笑分數是 {v['funny']}（滿分 10）。")
    lines += [f"編輯：{w}" for w in v["why"]]
    lines.append("寫新的一稿：前三格只鋪陳，指向結局的動作、道具、台詞全部留到第四格；"
                 "結局換到讀者想的方向以外，需要的話整個題材的切入點一起換。")
    return "\n".join(lines)


def _selftest():
    seq = iter([{"guesses": ["a", "b", "c"]}, {"guessed": True, "hit": "b", "funny": 7, "why": "x"},
                {"guesses": ["a", "b", "c"]}, {"guessed": False, "hit": "", "funny": 6, "why": "y"}])
    v = judge("Panel 1: a Panel 2: b Panel 3: c Panel 4: d", ask=lambda p, t: next(seq))
    assert v == {"ok": False, "hits": ["b"], "funny": 6, "why": ["x", "y"], "runs": 2}, v
    seq = iter([{"guesses": ["a"]}, {"guessed": False, "funny": 4, "why": "z"}])
    v = judge("Panel 1: a Panel 4: d", runs=1, ask=lambda p, t: next(seq))
    assert v["ok"] is False and not v["hits"] and "4" in feedback(v), v
    seen = []
    def spy(p, t):
        seen.append(p)
        return {"guesses": ["a"]} if len(seen) == 1 else {"guessed": False, "funny": 8, "why": ""}
    assert judge("Panel 1: a Panel 3: c Panel 4: SECRET", runs=1, ask=spy)["ok"]
    assert "SECRET" not in seen[0] and "SECRET" in seen[1]      # 猜的時候看不到第四格
    def boom(p, t): raise RuntimeError("down")
    global time
    class _T:                                                    # 自測不真的等
        sleep = staticmethod(lambda s: None)
    real, time = time, _T
    try:
        assert judge("Panel 1: a Panel 4: d", ask=boom) is None
    finally:
        time = real
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--selftest"]:
        _selftest()
    elif a[:1] == ["--day"]:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        es = json.load(open(os.path.join(root, "docs/entries.json")))
        e = next(x for x in (es if isinstance(es, list) else es["entries"]) if x["day"] == int(a[1]))
        print(json.dumps(judge(e["comic"]), ensure_ascii=False, indent=1))
    elif a[:1] == ["--text"]:
        print(json.dumps(judge(open(a[1], encoding="utf-8").read()), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
