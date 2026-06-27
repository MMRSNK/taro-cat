"""Generate 78 placeholder card PNGs in cards/ so the pipeline runs before
real scans exist. Skips files that already exist (won't overwrite real scans).

CLI:  python tools/make_placeholder_cards.py [--force]
"""
import json
import sys

from PIL import Image, ImageDraw

from compose_image import CARD_W, CARD_H, _font, _draw_wrapped
from config import CARDS_DIR, CARDS_JSON

ACCENT = (198, 167, 94)
FG = (240, 235, 250)


def make(force=False):
    cards = json.load(open(CARDS_JSON, encoding="utf-8"))
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    for card in cards:
        out = CARDS_DIR / card["image"]
        if out.exists() and not force:
            continue
        img = Image.new("RGB", (CARD_W, CARD_H), (44, 34, 66))
        d = ImageDraw.Draw(img)
        d.rectangle([6, 6, CARD_W - 7, CARD_H - 7], outline=ACCENT, width=4)
        _draw_wrapped(d, card["name_uk"], _font(34), CARD_W,
                      start_y=CARD_H // 2 - 60, fill=FG, center_x=CARD_W // 2)
        label = card["id"]
        d.text((16, CARD_H - 36), label, font=_font(20), fill=ACCENT)
        img.save(out, "PNG")
        created += 1
    print(f"created {created} placeholder card(s) in {CARDS_DIR}")


if __name__ == "__main__":
    make(force="--force" in sys.argv)
