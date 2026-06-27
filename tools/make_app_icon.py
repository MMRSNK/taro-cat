"""Generate a 1024x1024 app icon for the Threads/Meta app listing.

Output: docs/app_icon.png  (upload this in App settings -> App icon)
Run:    python tools/make_app_icon.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

from compose_image import _font

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "app_icon.png"

S = 1024
BG_TOP = (38, 26, 64)
BG_BOT = (18, 14, 30)
GOLD = (210, 178, 100)
GOLD_SOFT = (170, 142, 78)
FG = (240, 235, 250)


def _vgrad(size, top, bot):
    base = Image.new("RGB", (1, size), 0)
    for y in range(size):
        t = y / (size - 1)
        base.putpixel((0, y), tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    return base.resize((size, size))


def star(d, cx, cy, r, fill):
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i
        rr = r if i % 2 == 0 else r * 0.4
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=fill)


def make():
    img = _vgrad(S, BG_TOP, BG_BOT)
    d = ImageDraw.Draw(img)

    cx = S // 2

    # crescent moon (gold disc minus offset disc)
    moon = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(moon)
    md.ellipse([cx - 150, 170, cx + 150, 470], fill=255)
    md.ellipse([cx - 80, 150, cx + 220, 450], fill=0)
    img.paste(Image.new("RGB", (S, S), GOLD), (0, 0), moon)

    # stars
    for (x, y, r) in [(300, 250, 18), (720, 300, 14), (360, 430, 10),
                      (680, 470, 11), (520, 180, 12), (250, 360, 8)]:
        star(d, x, y, r, GOLD)

    # three fanned tarot cards
    cards = [(-22, cx - 250, 520), (0, cx - 90, 550), (22, cx + 70, 520)]
    cw, ch = 190, 300
    for ang, x, y in cards:
        card = Image.new("RGBA", (cw + 40, ch + 40), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle([20, 20, cw + 20, ch + 20], radius=16,
                             fill=(46, 36, 70), outline=GOLD, width=6)
        cd.ellipse([cw // 2 - 18, ch // 2 - 18 + 20, cw // 2 + 18 + 20, ch // 2 + 18 + 20],
                   outline=GOLD_SOFT, width=4)
        rot = card.rotate(ang, expand=True, resample=Image.BICUBIC)
        img.paste(rot, (int(x), int(y)), rot)

    # wordmark
    f = _font(135)
    txt = "ТАРО"
    box = d.textbbox((0, 0), txt, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text((cx - w // 2, 1010 - h - box[1]), txt, font=f, fill=FG)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG")
    print("wrote", OUT, img.size)


if __name__ == "__main__":
    make()
