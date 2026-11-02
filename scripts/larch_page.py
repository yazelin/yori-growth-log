"""日記頁背景 1920×1080：夜裡的森林，一頁奶油紙，左欄寫日期標題，右邊貼當句的圖（整張四格或放大其中一格）。

避開的區域（Larch 實測）：上方約 90px 有播放器與預覽的按鈕列，y≈756 以下是對話框，x≥1250 站立繪。
"""
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


def _forest():
    global _bg
    if _bg is None:
        f = Image.open(ROOT / "larch/forest.jpg").convert("RGB").resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(8))
        glow = Image.new("L", (W, H), 0)
        ImageDraw.Draw(glow).ellipse((W * .1, H * .05, W * .9, H * 1.05), fill=60)
        glow = glow.filter(ImageFilter.GaussianBlur(160))
        _bg = Image.composite(Image.new("RGB", (W, H), (236, 200, 116)), f, glow)
    return _bg.copy()


def _wrap(text, n):
    """每行最多 n 字，行數不變的前提下平均分，不留一個字自己一行"""
    rows = -(-len(text) // n)
    per = -(-len(text) // rows) if rows else n
    return [text[i:i + per] for i in range(0, len(text), per)]


def render(p, out, src, panel=None, boxes=None):
    """src：四格原圖路徑。panel=None 放整張；1–4 放大那一格（boxes 是 find_panels 的結果）。"""
    bg = _forest()
    d = ImageDraw.Draw(bg)
    # 紙：陰影＋奶油底＋點陣
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle(PAPER, 14, fill=150)
    bg.paste((10, 14, 10), (0, 0), sh.filter(ImageFilter.GaussianBlur(22)))
    d.rounded_rectangle(PAPER, 14, fill=(243, 234, 211))
    for y in range(PAPER[1] + 24, PAPER[3] - 10, 24):
        for x in range(PAPER[0] + 24, PAPER[2] - 10, 24):
            d.point((x, y), fill=(222, 210, 180))
    # 左欄：Day、日期、標題
    x0 = PAPER[0] + 44
    d.text((x0, 130), f"Day {p['day']:04d}", font=ImageFont.truetype(str(FONT_R), 34), fill=PENCIL)
    m, dd = int(p["date"][5:7]), int(p["date"][8:])
    d.text((x0, 176), f"{m} 月 {dd} 日", font=ImageFont.truetype(str(FONT_R), 34), fill=PENCIL)
    y = 250
    tf = ImageFont.truetype(str(FONT_B), 46)
    for ln in _wrap(p["title"], 6)[:5]:
        d.text((x0, y), ln, font=tf, fill=LEATHER)
        y += 62
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
