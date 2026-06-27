"""Compose the 3 drawn card scans into one forecast image (Pillow).

- Reversed cards are rotated 180°.
- Missing scans fall back to a generated placeholder tile, so the pipeline
  works before real scans are added.
- No network, no paid APIs.

CLI (uses placeholders/scans, no API):  python tools/compose_image.py
"""
import os
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import CARDS_DIR, TMP_DIR, ROOT

BG_IMAGE = ROOT / "assets" / "post_bg.png"

# Layout constants
BG = (24, 18, 38)          # deep purple
FG = (240, 235, 250)
ACCENT = (198, 167, 94)    # gold
CARD_W, CARD_H = 360, 600
GAP = 36
MARGIN = 48
TITLE_H = 110
CAPTION_H = 90

FONT_CANDIDATES = [
    os.getenv("FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _font(size):
    for path in FONT_CANDIDATES:
        if path and Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _placeholder_tile(card):
    img = Image.new("RGB", (CARD_W, CARD_H), (44, 34, 66))
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, CARD_W - 7, CARD_H - 7], outline=ACCENT, width=4)
    f = _font(34)
    _draw_wrapped(d, card["name_uk"], f, CARD_W, start_y=CARD_H // 2 - 60,
                  fill=FG, center_x=CARD_W // 2)
    return img


def _card_tile(card):
    path = CARDS_DIR / card["image"]
    if path.exists():
        img = Image.open(path).convert("RGB").resize((CARD_W, CARD_H))
    else:
        img = _placeholder_tile(card)
    if card.get("reversed"):
        img = img.rotate(180)
    return img


def _text_w(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _draw_wrapped(draw, text, font, max_w, start_y, fill, center_x):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if _text_w(draw, trial, font) <= max_w - 20 or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    y = start_y
    for line in lines:
        lw = _text_w(draw, line, font)
        draw.text((center_x - lw // 2, y), line, font=font, fill=fill)
        y += font.size + 6
    return y


def _cover(img, w, h):
    """Scale to cover (w,h) then center-crop."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    img = img.resize((int(iw * scale) + 1, int(ih * scale) + 1))
    x = (img.width - w) // 2
    y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def compose(cards, title="Таро прогноз", subtitle="", out_dir=TMP_DIR):
    n = len(cards)
    width = MARGIN * 2 + n * CARD_W + (n - 1) * GAP
    height = MARGIN + TITLE_H + CARD_H + CAPTION_H + MARGIN

    if BG_IMAGE.exists():
        canvas = _cover(Image.open(BG_IMAGE).convert("RGB"), width, height)
        veil = Image.new("RGBA", (width, height), (10, 8, 20, 60))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), veil).convert("RGB")
    else:
        canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    # Title + optional subtitle
    title_font = _font(46)
    tw = _text_w(draw, title, title_font)
    draw.text(((width - tw) // 2, MARGIN), title, font=title_font, fill=ACCENT)
    if subtitle:
        sub_font = _font(26)
        _draw_wrapped(draw, subtitle, sub_font, width - 2 * MARGIN,
                      start_y=MARGIN + 56, fill=FG, center_x=width // 2)

    # Card row + captions
    cap_font = _font(24)
    y_cards = MARGIN + TITLE_H
    for i, card in enumerate(cards):
        x = MARGIN + i * (CARD_W + GAP)
        canvas.paste(_card_tile(card), (x, y_cards))
        arrow = "↓ перевернута" if card.get("reversed") else "↑ пряма"
        cap = f"{card['name_uk']}"
        _draw_wrapped(draw, cap, cap_font, CARD_W, start_y=y_cards + CARD_H + 6,
                      fill=FG, center_x=x + CARD_W // 2)
        aw = _text_w(draw, arrow, cap_font)
        draw.text((x + (CARD_W - aw) // 2, y_cards + CARD_H + 6 + 2 * (cap_font.size + 6)),
                  arrow, font=cap_font, fill=ACCENT)

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"forecast_{stamp}.png"
    canvas.save(out, "PNG")
    return out


if __name__ == "__main__":
    from draw_cards import draw as draw_cards
    cards = draw_cards(3)
    p = compose(cards, title="Таро прогноз", subtitle="тестовий розклад")
    print("wrote", p)
