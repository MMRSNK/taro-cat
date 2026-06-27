"""Upscale / enhance tarot card crops via Vertex AI express (Google Gen AI SDK).

Uses an API key only (vertexai=True, api_key=...) — no projectId/appId needed.
Set the key in env GOOGLE_CLOUD_API_KEY (or GEMINI_API_KEY).

Test ONE card first (fidelity check), then run all:
    GOOGLE_CLOUD_API_KEY=... python tools/upscale_cards.py --only major_00
    GOOGLE_CLOUD_API_KEY=... python tools/upscale_cards.py --all --resume

Input : images-final/_crops/<id>.png
Output: images-final-hq/<id>.png
"""
import argparse
import os
import time
from pathlib import Path

from config import ROOT  # also sets utf-8 stdout

SRC = ROOT / "images-final"          # named crops live here (<id>.png)
OUT = ROOT / "images-final-hq"
MODEL = "gemini-3.1-flash-image"  # nano banana 2

PROMPT = (
    "Clean up and upscale this scanned tarot card. REMOVE the uneven black scanner margin "
    "and the crooked/skewed black background around the card, and straighten the card so it "
    "sits upright and fills the frame cleanly as a neat rectangle. "
    "KEEP the card itself unchanged: its own decorative border, the cat character, pose, "
    "composition, colors, art style AND the Ukrainian title text at the bottom must stay "
    "exactly the same. Do not redraw the artwork, do not add or remove elements, no new text. "
    "Output crisp high resolution, portrait aspect ratio."
)


def make_client():
    from google import genai

    key = os.environ.get("GOOGLE_CLOUD_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("set GOOGLE_CLOUD_API_KEY (or GEMINI_API_KEY)")
    return genai.Client(vertexai=True, api_key=key)


def enhance(client, cid):
    from google.genai import types

    img = (SRC / f"{cid}.png").read_bytes()
    cfg = types.GenerateContentConfig(
        temperature=1,
        top_p=0.95,
        max_output_tokens=32768,
        response_modalities=["TEXT", "IMAGE"],
        safety_settings=[
            types.SafetySetting(category=c, threshold="OFF")
            for c in ("HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_DANGEROUS_CONTENT",
                      "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_HARASSMENT")
        ],
        image_config=types.ImageConfig(image_size="2K"),
    )
    contents = [PROMPT, types.Part.from_bytes(data=img, mime_type="image/png")]
    resp = None
    for attempt in range(6):
        try:
            resp = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
            break
        except Exception as e:
            msg = str(e)
            transient = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg or "500" in msg
            if not transient or attempt == 5:
                raise
            wait = 20 * (attempt + 1)  # 20,40,60,80,100s
            print(f"[429/transient] wait {wait}s ...", end=" ", flush=True)
            time.sleep(wait)
    for cand in (resp.candidates or []):
        for p in (cand.content.parts or []):
            if getattr(p, "inline_data", None) and p.inline_data.data:
                OUT.mkdir(parents=True, exist_ok=True)
                _save_trimmed(p.inline_data.data, OUT / f"{cid}.png")
                return True
    raise RuntimeError("no image part in response")


def _save_trimmed(png_bytes, out_path):
    """Trim the near-white margin the model adds around the cleaned card."""
    import io
    import numpy as np
    from PIL import Image

    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    a = np.asarray(im)
    nonwhite = ~((a[:, :, 0] > 235) & (a[:, :, 1] > 235) & (a[:, :, 2] > 235))
    rows = np.where(nonwhite.any(axis=1))[0]
    cols = np.where(nonwhite.any(axis=0))[0]
    if len(rows) and len(cols):
        im = im.crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))
    im.save(out_path, "PNG")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()

    client = make_client()
    if a.only:
        ids = [a.only]
    else:
        ids = sorted(p.stem for p in SRC.glob("*.png"))

    done = 0
    for cid in ids:
        if a.resume and (OUT / f"{cid}.png").exists():
            print(f"skip {cid} (exists)")
            continue
        try:
            print(f"enhancing {cid} ...", end=" ", flush=True)
            enhance(client, cid)
            print("ok")
            done += 1
            time.sleep(1.0)
        except Exception as e:
            print(f"FAIL: {e}")
    print(f"\ndone: {done}/{len(ids)} -> {OUT}")


if __name__ == "__main__":
    main()
