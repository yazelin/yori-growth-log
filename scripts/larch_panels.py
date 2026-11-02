"""找四格的四個框：四格是奶油底上 2×2 的黑框格子，格子之間是亮色的溝。
找法：看哪些列／欄幾乎整條都是亮的（溝），取最靠近預期位置的那條。"""
import numpy as np
from PIL import Image


def _runs(mask):
    """mask 裡連續 True 的區段 [(start, end)]"""
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        if not v and s is not None:
            out.append((s, i)); s = None
    if s is not None:
        out.append((s, len(mask)))
    return out


def find_panels(path):
    a = np.asarray(Image.open(path).convert("L"), np.float32)
    h, w = a.shape
    bright = a > 200
    # 溝：整條 90% 以上是亮的
    cols = bright[int(h * .2):int(h * .95)].mean(0) > .9
    rows = bright[:, int(w * .05):int(w * .95)].mean(1) > .9
    vc = [r for r in _runs(cols) if .35 * w < (r[0] + r[1]) / 2 < .65 * w]
    hr_mid = [r for r in _runs(rows) if .4 * h < (r[0] + r[1]) / 2 < .65 * h]
    hr_top = [r for r in _runs(rows) if .04 * h < (r[0] + r[1]) / 2 < .22 * h]
    if not (vc and hr_mid):
        return None
    x = min(vc, key=lambda r: abs((r[0] + r[1]) / 2 - w / 2))
    ym = min(hr_mid, key=lambda r: abs((r[0] + r[1]) / 2 - h * .53))
    # 左右下邊界：從外往內找第一個不是亮的
    edge_c = bright[int(h * .2):int(h * .95)].mean(0) > .9
    l = next(i for i in range(w) if not edge_c[i]); r = next(i for i in range(w - 1, -1, -1) if not edge_c[i]) + 1
    edge_r = bright[:, int(w * .05):int(w * .95)].mean(1) > .9
    b = next(i for i in range(h - 1, -1, -1) if not edge_r[i]) + 1
    # 有標題列就從標題下面那條溝開始，沒有就從最上面第一條不亮的列開始
    t = max(hr_top, key=lambda r: r[1])[1] if hr_top else next(i for i in range(h) if not edge_r[i])
    boxes = [(l, t, x[0], ym[0]), (x[1], t, r, ym[0]), (l, ym[1], x[0], b), (x[1], ym[1], r, b)]
    # 四格大小要差不多，不然當作沒找到
    areas = [(q[2] - q[0]) * (q[3] - q[1]) for q in boxes]
    if min(areas) < .6 * max(areas) or min(areas) < .1 * w * h:
        return None
    return boxes


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    repo = Path.home() / "yori-growth-log"
    ok = bad = 0
    for e in json.loads((repo / "docs/entries.json").read_text()):
        md = (repo / e["entry_markdown"]).read_text()
        if "Four-panel" not in md:
            continue
        p = find_panels(repo / e["image"])
        ok += p is not None; bad += p is None
        if p is None or "-v" in sys.argv:
            print(e["day"], p)
    print("found", ok, "missing", bad)
