"""Upload an image to a public host, return its direct URL.

Threads requires images at a public URL. Default host is catbox.moe — no account,
no API key, permanent direct links. Switch host via env IMAGE_HOST.

Providers:
  catbox   (default) — https://catbox.moe, no creds, permanent
  tmpfiles           — https://tmpfiles.org, no creds, link valid ~1h (fine: Threads
                       fetches the image during publish, within seconds)
  litterbox          — https://litterbox.catbox.moe, no creds, catbox's temp sibling,
                       direct image/* link valid 72h (Meta-friendly, separate infra
                       from catbox so it survives a catbox hiccup)
  imgur              — needs IMGUR_CLIENT_ID

CLI (real upload):  python tools/upload_image.py path/to/image.png
"""
import base64
import sys
import time
from pathlib import Path

import requests

from config import require, settings

# Some hosts reject the default python-requests User-Agent. Send a plain UA.
_UA = "taro-bot/1.0 (+https://github.com)"


def upload_catbox(image_path):
    p = Path(image_path)
    body = p.read_bytes()
    last = ""
    # catbox intermittently answers 200 with an empty/non-URL body (transient
    # rate-limit/hiccup). Retry a couple times before giving up on the host.
    for i in range(3):
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (p.name, body, "image/png")},
            headers={"User-Agent": _UA},
            timeout=120,
        )
        url = resp.text.strip()
        if resp.status_code == 200 and url.startswith("http"):
            return url
        last = f"catbox upload failed [{resp.status_code}]: {resp.text[:200]}"
        time.sleep(2 * (i + 1))  # 2s, 4s
    raise RuntimeError(last)


def upload_litterbox(image_path):
    p = Path(image_path)
    resp = requests.post(
        "https://litterbox.catbox.moe/resources/internals/api.php",
        data={"reqtype": "fileupload", "time": "72h"},
        files={"fileToUpload": (p.name, p.read_bytes(), "image/png")},
        headers={"User-Agent": _UA},
        timeout=120,
    )
    url = resp.text.strip()
    if resp.status_code != 200 or not url.startswith("http"):
        raise RuntimeError(f"litterbox upload failed [{resp.status_code}]: {resp.text[:200]}")
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
    "litterbox": upload_litterbox,
    "imgur": upload_imgur,
}


def upload(image_path, host=None):
    """Upload to `host` (defaults to IMAGE_HOST). Returns the public direct URL."""
    host = (host or settings.IMAGE_HOST or "catbox").lower()
    fn = _PROVIDERS.get(host)
    if not fn:
        raise SystemExit(f"unknown image host {host!r}; pick one of {list(_PROVIDERS)}")
    return fn(image_path)


def host_order():
    """Hosts to try, primary (IMAGE_HOST) first, the rest as fallbacks. Used when
    Threads can't fetch the image from one host (subcode 2207003) so the post can
    be retried from another. imgur is skipped unless IMGUR_CLIENT_ID is set."""
    primary = (settings.IMAGE_HOST or "catbox").lower()
    # catbox/litterbox first among fallbacks: they serve a raw image/* Content-Type,
    # so Meta's fetcher doesn't hit the 2207083 "bad format" that tmpfiles can trigger.
    order = [primary] + [h for h in ("catbox", "litterbox", "tmpfiles", "imgur") if h != primary]
    if not settings.IMGUR_CLIENT_ID:
        order = [h for h in order if h != "imgur"]
    return order


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/upload_image.py <image_path>")
    print(upload(sys.argv[1]))
