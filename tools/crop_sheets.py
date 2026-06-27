"""Split scanned tarot sheets (2 rows x 3 cols = 6 cards each) into single cards.

Uses brightness projection profiles to find the black gaps between cards, so it
tolerates small offsets/skew and trims the outer black margins. Each cell is then
tightened to the card's bounding box.

CLI:
    python tools/crop_sheets.py --sheet images-raw/IMG_..._0001.jpg --test   # 6 crops + montage to .tmp/
    python tools/crop_sheets.py --all images-raw --out images-final/_crops    # all sheets, position-named
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

MARGIN_T = 28       # line-mean below this = near-black outer margin to trim
PAD = 5             # px kept around the trimmed card


def _smooth(a, k=21):
    return np.convolve(a, np.ones(k) / k, mode="same")


def _minima(a, lo, hi, count, sep_frac=0.12):
    """Indices of the `count` deepest minima within [lo,hi] fraction, spaced apart."""
    region = np.arange(int(len(a) * lo), int(len(a) * hi))
    order = region[np.argsort(a[region])]
    picks = []
    for i in order:
        if all(abs(i - p) > len(a) * sep_frac for p in picks):
            picks.append(int(i))
        if len(picks) == count:
            break
    return sorted(picks)


def _trim(cell):
    """Trim only the near-black outer margin (keeps dark cards intact)."""
    a = np.asarray(cell.convert("L"), dtype=np.float32)
    rmean, cmean = a.mean(axis=1), a.mean(axis=0)

    def edges(m):
        on = np.where(m > MARGIN_T)[0]
        return (on[0], on[-1] + 1) if len(on) else (0, len(m))

    y0, y1 = edges(rmean)
    x0, x1 = edges(cmean)
    return cell.crop((max(x0 - PAD, 0), max(y0 - PAD, 0),
                      min(x1 + PAD, cell.width), min(y1 + PAD, cell.height)))


def split_sheet(path):
    """Return 6 PIL card images in row-major order (TL,TM,TR,BL,BM,BR)."""
    im = Image.open(path).convert("RGB")
    g = np.asarray(im.convert("L"), dtype=np.float32)
    H, W = g.shape

    vg = _minima(_smooth(g.mean(axis=0)), 0.15, 0.85, 2)   # 2 vertical gaps
    hg = _minima(_smooth(g.mean(axis=1)), 0.30, 0.70, 1)   # 1 horizontal gap
    if len(vg) != 2 or len(hg) != 1:
        raise RuntimeError(f"{Path(path).name}: gaps v={vg} h={hg} (expected 2/1)")

    xcuts = [0] + vg + [W]
    ycuts = [0] + hg + [H]
    cards = []
    for r in range(2):
        for c in range(3):
            cell = im.crop((xcuts[c], ycuts[r], xcuts[c + 1], ycuts[r + 1]))
            cards.append(_trim(cell))
    return cards


def montage(cards, scale=0.35):
    w = max(c.width for c in cards)
    h = max(c.height for c in cards)
    cols, rows = 3, 2
    canvas = Image.new("RGB", (cols * w, rows * h), (10, 10, 10))
    for i, c in enumerate(cards):
        canvas.paste(c, ((i % 3) * w, (i // 3) * h))
    return canvas.resize((int(canvas.width * scale), int(canvas.height * scale)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--all")
    ap.add_argument("--out", default="images-final/_crops")
    a = ap.parse_args()

    if a.sheet:
        cards = split_sheet(a.sheet)
        td = ROOT / ".tmp"; td.mkdir(exist_ok=True)
        for i, c in enumerate(cards):
            c.save(td / f"croptest_{i}.png")
        montage(cards).save(td / "croptest_montage.png")
        print("wrote 6 crops + montage to .tmp/  sizes:", [c.size for c in cards])
    elif a.all:
        out = ROOT / a.out
        out.mkdir(parents=True, exist_ok=True)
        sheets = sorted(Path(a.all).glob("*.jpg"))
        for si, sp in enumerate(sheets, 1):
            cards = split_sheet(sp)
            for pi, c in enumerate(cards):
                c.save(out / f"sheet{si:02d}_p{pi}.png")
            print(f"{sp.name}: 6 crops")
        print(f"done -> {out}")
