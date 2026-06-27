"""Bulk-import card scans and rename them to the bot's filename convention.

Scan all 78 cards IN DECK ORDER, name them anything sortable (01..78, or a.jpg,
b.jpg...), drop them in one folder, then run this. Each i-th image is mapped to the
i-th card in data/cards.json order:
    Major 0..21, then Cups (ace,2..10,page,knight,queen,king), Wands, Swords, Pentacles.

Always preview first:
    python tools/import_scans.py /path/to/scans --dry-run
Then import (converts to PNG into cards/):
    python tools/import_scans.py /path/to/scans
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image

from config import CARDS_DIR, CARDS_JSON

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def natkey(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def main(src, dry=False):
    cards = json.load(open(CARDS_JSON, encoding="utf-8"))
    src = Path(src)
    if not src.is_dir():
        raise SystemExit(f"not a folder: {src}")

    imgs = sorted([p for p in src.iterdir() if p.suffix.lower() in IMG_EXT], key=natkey)
    print(f"found {len(imgs)} images, deck needs {len(cards)}")
    if len(imgs) != len(cards):
        print("!! count mismatch — fix before a real import (need exactly 78 in deck order)")

    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for img, card in zip(imgs, cards):
        print(f"  {img.name:<24} -> {card['image']:<22} ({card['name_uk']})")
        if not dry:
            Image.open(img).convert("RGB").save(CARDS_DIR / card["image"], "PNG")
            n += 1
    print("DRY-RUN: nothing written" if dry else f"imported {n} scans -> {CARDS_DIR}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if not args:
        raise SystemExit("usage: python tools/import_scans.py <scans_folder> [--dry-run]")
    main(args[0], dry="--dry-run" in sys.argv)
