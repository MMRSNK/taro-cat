"""Map the position-named crops (sheetNN_pM) to real card filenames.

MAPPING was built by reading the printed Ukrainian label on each card (row-major:
TL,TM,TR,BL,BM,BR per sheet). Verifies all 78 ids are covered exactly once, then
writes correctly-named PNGs to images-final/ and copies them into cards/.

CLI:  python tools/name_crops.py
"""
import json
import shutil
from pathlib import Path

from config import CARDS_DIR, CARDS_JSON

ROOT = Path(__file__).resolve().parent.parent
CROPS = ROOT / "images-final" / "_crops"
FINAL = ROOT / "images-final"

# 13 sheets x 6 cards, row-major (TL,TM,TR,BL,BM,BR)
MAPPING = [
    ["major_14", "cups_08", "wands_02", "major_19", "pentacles_page", "swords_page"],
    ["major_12", "cups_06", "cups_page", "wands_09", "pentacles_08", "major_09"],
    ["major_06", "pentacles_02", "swords_ace", "major_20", "swords_queen", "wands_06"],
    ["swords_07", "wands_queen", "pentacles_ace", "major_18", "major_17", "major_05"],
    ["wands_page", "cups_02", "cups_05", "swords_10", "major_15", "wands_03"],
    ["wands_knight", "swords_08", "swords_king", "cups_04", "swords_09", "major_13"],
    ["major_03", "major_21", "swords_03", "pentacles_03", "pentacles_knight", "cups_king"],
    ["cups_queen", "major_00", "cups_ace", "wands_king", "swords_knight", "pentacles_queen"],
    ["pentacles_05", "cups_09", "major_01", "wands_ace", "major_04", "swords_05"],
    ["swords_04", "cups_07", "swords_06", "wands_08", "major_16", "major_08"],
    ["major_02", "pentacles_10", "major_07", "pentacles_09", "wands_10", "swords_02"],
    ["wands_04", "cups_10", "wands_07", "pentacles_06", "pentacles_04", "wands_05"],
    ["cups_knight", "major_10", "major_11", "pentacles_07", "cups_03", "pentacles_king"],
]


def main():
    deck_ids = {c["id"] for c in json.load(open(CARDS_JSON, encoding="utf-8"))}
    flat = [cid for sheet in MAPPING for cid in sheet]

    # ---- verify ----
    assert len(flat) == 78, f"mapping has {len(flat)} entries, expected 78"
    dupes = {x for x in flat if flat.count(x) > 1}
    missing = deck_ids - set(flat)
    unknown = set(flat) - deck_ids
    if dupes or missing or unknown:
        raise SystemExit(f"VERIFY FAILED  dupes={dupes}  missing={missing}  unknown={unknown}")
    print("verify OK: 78 unique ids, all match the deck")

    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for si, sheet in enumerate(MAPPING, 1):
        for pi, cid in enumerate(sheet):
            src = CROPS / f"sheet{si:02d}_p{pi}.png"
            if not src.exists():
                raise SystemExit(f"missing crop: {src}")
            dst_final = FINAL / f"{cid}.png"
            dst_card = CARDS_DIR / f"{cid}.png"
            shutil.copyfile(src, dst_final)
            shutil.copyfile(src, dst_card)
            n += 1
    print(f"named {n} cards -> {FINAL} and {CARDS_DIR}")


if __name__ == "__main__":
    main()
