"""Upload an image to Imgur, return its public URL.

Threads requires images to be hosted at a public URL; Imgur provides that.
Uses anonymous upload with a free client_id (IMGUR_CLIENT_ID).

CLI (real API call):  python tools/upload_imgur.py path/to/image.png
"""
import base64
import sys
from pathlib import Path

import requests

from config import require, settings

IMGUR_URL = "https://api.imgur.com/3/image"


def upload(image_path):
    require("IMGUR_CLIENT_ID")
    image_path = Path(image_path)
    data = base64.b64encode(image_path.read_bytes())

    resp = requests.post(
        IMGUR_URL,
        headers={"Authorization": f"Client-ID {settings.IMGUR_CLIENT_ID}"},
        data={"image": data, "type": "base64"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Imgur upload failed [{resp.status_code}]: {resp.text}")
    link = resp.json()["data"]["link"]
    return link


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/upload_imgur.py <image_path>")
    print(upload(sys.argv[1]))
