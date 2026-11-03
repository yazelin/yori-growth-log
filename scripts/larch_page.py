"""日記頁背景 1920×1080：夜裡的森林，一頁奶油紙，左欄寫日期標題，右邊貼當句的圖（整張四格或放大其中一格）。

避開的區域（Larch 實測）：上方約 90px 有播放器與預覽的按鈕列，y≈756 以下是對話框，x≥1250 站立繪。
"""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_R = ROOT / "larch/fonts/LXGWWenKaiTC-Regular.ttf"  # 只留 Big5 字集的子集
FONT_B = ROOT / "larch/fonts/LXGWWenKaiTC-Bold.ttf"
W, H = 1920, 1080
PAPER = (40, 92, 1215, 742)          # 紙
IMG = (360, 118, 1190, 718)          # 圖可以放的範圍
INK, PENCIL, GOLD, LEATHER, CYAN = (43, 42, 34), (150, 138, 110), (201, 162, 74), (31, 58, 43), (63, 214, 200)

_bg = None
_sh = None


def _sheet():
    global _sh
    if _sh is None:
        _sh = Image.open(ROOT / "larch/sheet.webp").convert("RGBA")
    return _sh


def _forest():
    global _bg
    if _bg is None:
        f = Image.open(ROOT / "docs/larch/ui/forest.webp").convert("RGB").resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
        glow = Image.new("L", (W, H), 0)
        ImageDraw.Draw(glow).ellipse((W * .1, H * .05, W * .9, H * 1.05), fill=60)
        glow = glow.filter(ImageFilter.GaussianBlur(160))
        _bg = Image.composite(Image.new("RGB", (W, H), (236, 200, 116)), f, glow)
    return _bg.copy()


PUNCT = set("，。、；：！？）」』》 ")
SOFT = set("的了再先就要把讓和與也還才在是到")  # 斷在這些字後面，讀起來比較順


def _wrap(text, font, maxw):
    """在不超過 maxw 的前提下，行數最少、斷點盡量落在標點或虛字後面、各行長度接近。
    英文單字中間不斷；標點不放行首（會跟著上一行，允許稍微超出）。"""
    n = len(text)

    def cut_cost(i):  # 在 text[i] 前面斷
        a, b = text[i - 1], text[i]
        if b in PUNCT:
            return None
        if a.isascii() and a.isalnum() and b.isascii() and b.isalnum():
            return None
        return 0 if a in PUNCT else 1 if a in SOFT or a.isascii() or b.isascii() else 4

    best = {0: (0, 0, [])}  # 位置 -> (行數, 代價, 各行)
    for i in range(n):
        if i not in best:
            continue
        rows, cost, lines = best[i]
        for j in range(i + 1, n + 1):
            ln = text[i:j].strip()
            if font.getlength(ln.rstrip("".join(PUNCT))) > maxw:
                break
            c = 0 if j == n else cut_cost(j)
            if c is None:
                continue
            cand = (rows + 1, cost + c, lines + [ln])
            # 同樣好的斷法裡，選各行長度最接近的
            key = lambda x: (x[0], x[1], max(map(len, x[2])) - min(map(len, x[2])))
            if j not in best or key(cand) < key(best[j]):
                best[j] = cand
    if n not in best:  # 一個字都塞不下的極端情況，照字數硬切
        return [text[i:i + 6] for i in range(0, n, 6)]
    rows, _, lines = best[n]
    return lines


TITLES = ROOT / "larch/titles.json"  # 標題 -> 模型斷好的各行
TITLE_W = 6 * 42                      # 左欄寬：42px 的字約 6 個
TITLE_PROMPT = """下面每一行是一篇日記的標題。要排進很窄的直欄，每行最多約 6 個中文字（英文、數字、空格算半個字）。
替每個標題決定在哪裡換行：不要把一個詞拆開，盡量斷在標點、空格或「的、了、把」這類字後面，最多 5 行。
文字一個字都不能改、不能增減，只決定換行位置。
只輸出 JSON 物件：{{"原標題": ["第一行", "第二行"]}}，每個標題都要有。

{titles}"""


def _fits(title, lines, font):
    return (lines and len(lines) <= 5 and "".join(lines).replace(" ", "") == title.replace(" ", "")
            and all(font.getlength(l.rstrip("".join(PUNCT))) <= TITLE_W + 21 for l in lines))


def ask_titles(titles):
    """還沒斷過的標題一次問模型，合格的存進 larch/titles.json；不合格的留給規則斷。"""
    from scripts.larch_faces import _ask
    cache = json.loads(TITLES.read_text("utf-8")) if TITLES.exists() else {}
    font = ImageFont.truetype(str(FONT_B), 42)
    todo = [t for t in dict.fromkeys(titles) if t not in cache and len(_wrap(t, font, TITLE_W)) > 1]
    if not todo:
        return
    try:
        out = json.loads(re.search(r"\{.*\}", _ask(TITLE_PROMPT.format(titles="\n".join(todo))), re.S).group(0))
    except Exception as e:  # noqa: BLE001  模型或網路出錯就全部用規則斷，下一班再問
        print("標題斷行詢問失敗：", e)
        return
    ok = {t: out[t] for t in todo if isinstance(out.get(t), list) and _fits(t, out[t], font)}
    print(f"標題斷行：問了 {len(todo)} 個，採用 {len(ok)} 個")
    cache.update(ok)
    TITLES.write_text(json.dumps(cache, ensure_ascii=False, indent=0), "utf-8")


def title_lines(title, font):
    cache = json.loads(TITLES.read_text("utf-8")) if TITLES.exists() else {}
    # 行尾的逗號頓號不畫：換行已經斷句，留著還會壓到右邊的圖
    return [l.strip().rstrip("，、；") or l.strip() for l in cache.get(title) or _wrap(title, font, TITLE_W)]


def render(p, out, src, panel=None, boxes=None):
    """src：四格原圖路徑。panel=None 放整張；1–4 放大那一格（boxes 是 find_panels 的結果）。"""
    bg = _forest()
    d = ImageDraw.Draw(bg)
    # 紙：生圖的手帳內頁（larch/sheet.webp，左邊皮革書背），陰影照紙的輪廓
    sheet = _sheet()
    sh = Image.new("L", (W, H), 0)
    sh.paste(sheet.getchannel("A").point(lambda v: v * 150 // 255), (PAPER[0] + 6, PAPER[1] + 14))
    bg.paste((10, 14, 10), (0, 0), sh.filter(ImageFilter.GaussianBlur(22)))
    bg.paste(sheet, PAPER[:2], sheet)
    # 左欄：Day、日期、標題
    x0 = PAPER[0] + 80  # 讓開左邊的皮革書背
    d.text((x0, 130), f"Day {p['day']:04d}", font=ImageFont.truetype(str(FONT_R), 34), fill=PENCIL)
    m, dd = int(p["date"][5:7]), int(p["date"][8:])
    d.text((x0, 176), f"{m} 月 {dd} 日", font=ImageFont.truetype(str(FONT_R), 34), fill=PENCIL)
    y = 250
    tf = ImageFont.truetype(str(FONT_B), 42)
    for ln in title_lines(p["title"], tf)[:5]:
        d.text((x0, y), ln, font=tf, fill=LEATHER)
        y += 58
    # 小地圖：2×2 標出現在是第幾格
    if boxes:
        mx, my, s = x0, 620, 34
        for i in range(4):
            cx, cy = mx + (i % 2) * (s + 8), my + (i // 2) * (s + 8)
            on = panel is None or panel == i + 1
            d.rounded_rectangle((cx, cy, cx + s, cy + s), 5, fill=GOLD if on else None, outline=GOLD if on else PENCIL, width=3)
    # 圖：照片白框＋兩條紙膠帶
    im = Image.open(src).convert("RGB")
    if panel:
        im = im.crop(boxes[panel - 1])
    bw, bh = IMG[2] - IMG[0], IMG[3] - IMG[1]
    sc = min((bw - 28) / im.width, (bh - 28) / im.height)
    im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
    fw, fh = im.width + 28, im.height + 28
    fx, fy = IMG[0] + (bw - fw) // 2, IMG[1] + (bh - fh) // 2
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rectangle((fx + 4, fy + 8, fx + fw + 4, fy + fh + 8), fill=120)
    bg.paste((60, 45, 20), (0, 0), sh.filter(ImageFilter.GaussianBlur(10)))
    d.rectangle((fx, fy, fx + fw, fy + fh), fill=(255, 253, 245))
    bg.paste(im, (fx + 14, fy + 14))
    tape = Image.new("RGBA", (130, 38), (63, 214, 200, 105)).rotate(28, expand=True)
    bg.paste(tape, (fx - 50, fy - 40), tape)
    tape2 = tape.transpose(Image.FLIP_LEFT_RIGHT)
    bg.paste(tape2, (fx + fw - tape2.width + 50, fy - 40), tape2)
    bg.save(out, "WEBP", quality=84)
