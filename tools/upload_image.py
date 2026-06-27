"""Upload an image to a public host, return its direct URL.

Threads requires images at a public URL. Default host is catbox.moe — no account,
no API key, permanent direct links. Switch host via env IMAGE_HOST.

Providers:
  catbox   (default) — https://catbox.moe, no creds, permanent
  tmpfiles           — https://tmpfiles.org, no creds, link valid ~1h (fine: Threads
                       fetches the image during publish, within seconds)
  imgur              — needs IMGUR_CLIENT_ID

CLI (real upload):  python tools/upload_image.py path/to/image.png
"""
import base64
import sys
from pathlib import Path

import requests

from config import require, settings


def upload_catbox(image_path):
    p = Path(image_path)
    resp = requests.post(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": (p.name, p.read_bytes(), "image/png")},
        timeout=120,
    )
    url = resp.text.strip()
    if resp.status_code != 200 or not url.startswith("http"):
        raise RuntimeError(f"catbox upload failed [{resp.status_code}]: {resp.text[:200]}")
    return url


def upload_tmpfiles(image_path):
    p = Path(image_path)
    resp = requests.post(
        "https://tmpfiles.org/api/v1/upload",
        files={"file": (p.name, p.read_bytes(), "image/png")},
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"tmpfiles upload failed [{resp.status_code}]: {resp.text[:200]}")
    page = resp.json()["data"]["url"]              # e.g. https://tmpfiles.org/12345/x.png
    # convert to direct-download URL
    return page.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


def upload_imgur(image_path):
    require("IMGUR_CLIENT_ID")
    data = base64.b64encode(Path(image_path).read_bytes())
    resp = requests.post(
        "https://api.imgur.com/3/image",
        headers={"Authorization": f"Client-ID {settings.IMGUR_CLIENT_ID}"},
        data={"image": data, "type": "base64"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"imgur upload failed [{resp.status_code}]: {resp.text[:200]}")
    return resp.json()["data"]["link"]


_PROVIDERS = {
    "catbox": upload_catbox,
    "tmpfiles": upload_tmpfiles,
    "imgur": upload_imgur,
}


def upload(image_path):
    host = (settings.IMAGE_HOST or "catbox").lower()
    fn = _PROVIDERS.get(host)
    if not fn:
        raise SystemExit(f"unknown IMAGE_HOST={host!r}; pick one of {list(_PROVIDERS)}")
    return fn(image_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/upload_image.py <image_path>")
    print(upload(sys.argv[1]))
