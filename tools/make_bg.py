"""Generate the posting background via Nano Banana 2 (Vertex express).

Saves assets/post_bg.png — used by compose_image as the canvas backdrop.
    GOOGLE_CLOUD_API_KEY=... python tools/make_bg.py
"""
import io
import os

from PIL import Image

from config import ROOT

OUT = ROOT / "assets" / "post_bg.png"
MODEL = "gemini-3.1-flash-image"

PROMPT = (
    "A mystical tarot backdrop illustration, landscape orientation. "
    "Deep midnight indigo and purple night sky with a soft nebula, scattered tiny golden "
    "stars and a thin crescent moon in a top corner, an elegant faint golden art-nouveau "
    "ornamental frame around the edges. Atmospheric, painterly, subtle. "
    "Keep the CENTER dark, calm and uncluttered so three tarot cards can be placed on top. "
    "No text, no tarot cards, no characters, no animals."
)


def main():
    from google import genai
    from google.genai import types

    key = os.environ.get("GOOGLE_CLOUD_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("set GOOGLE_CLOUD_API_KEY")
    client = genai.Client(vertexai=True, api_key=key)

    def gen(image_config):
        return client.models.generate_content(
            model=MODEL,
            contents=[PROMPT],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"], image_config=image_config),
        )

    try:
        resp = gen(types.ImageConfig(image_size="2K", aspect_ratio="16:9"))
    except Exception as e:
        print("16:9 failed, retrying default ratio:", str(e)[:100])
        resp = gen(types.ImageConfig(image_size="2K"))

    for cand in (resp.candidates or []):
        for p in (cand.content.parts or []):
            if getattr(p, "inline_data", None) and p.inline_data.data:
                OUT.parent.mkdir(parents=True, exist_ok=True)
                Image.open(io.BytesIO(p.inline_data.data)).convert("RGB").save(OUT, "PNG")
                print("wrote", OUT, Image.open(OUT).size)
                return
    raise SystemExit("no image returned")


if __name__ == "__main__":
    main()
