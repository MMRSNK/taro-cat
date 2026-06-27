"""Publish to Threads via the official Threads Graph API.

Two-step flow per Meta docs:
  1) create a media container (image_url + text [+ reply_to_id])
  2) publish the container

Docs: https://developers.facebook.com/docs/threads

CLI (real API call):
    python tools/threads_post.py --image-url URL --text "..." [--reply-to ID]
"""
import argparse
import time

import requests

from config import require, settings

THREADS_TEXT_LIMIT = 500


def clamp_text(text, limit=THREADS_TEXT_LIMIT):
    """Trim to the Threads limit, preferring a clean sentence boundary."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    for sep in (". ", "! ", "? ", "\n", " "):
        idx = cut.rfind(sep)
        if idx > limit * 0.6:
            return cut[: idx + 1].strip() + "…"
    return cut.strip() + "…"


def _base():
    return f"{settings.THREADS_API_BASE}/{settings.THREADS_USER_ID}"


def create_container(text, image_url=None, reply_to_id=None):
    require("THREADS_USER_ID", "THREADS_ACCESS_TOKEN")
    params = {
        "access_token": settings.THREADS_ACCESS_TOKEN,
        "text": clamp_text(text),
    }
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"
    if reply_to_id:
        params["reply_to_id"] = reply_to_id

    r = requests.post(f"{_base()}/threads", data=params, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"create container failed [{r.status_code}]: {r.text}")
    return r.json()["id"]


def wait_ready(container_id, attempts=10, delay=3):
    """Poll container status until FINISHED (image containers may need a moment)."""
    for _ in range(attempts):
        r = requests.get(
            f"{settings.THREADS_API_BASE}/{container_id}",
            params={"fields": "status",
                    "access_token": settings.THREADS_ACCESS_TOKEN},
            timeout=30,
        )
        status = r.json().get("status") if r.status_code == 200 else None
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"container {container_id} processing ERROR: {r.text}")
        time.sleep(delay)
    # Best-effort: continue to publish even if status never reported FINISHED.


def publish(container_id):
    r = requests.post(
        f"{_base()}/threads_publish",
        data={"creation_id": container_id,
              "access_token": settings.THREADS_ACCESS_TOKEN},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"publish failed [{r.status_code}]: {r.text}")
    return r.json()["id"]


def post(text, image_url=None, reply_to_id=None):
    """Convenience: create -> wait -> publish. Returns published media id."""
    cid = create_container(text, image_url=image_url, reply_to_id=reply_to_id)
    if image_url:
        wait_ready(cid)
    return publish(cid)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image-url")
    ap.add_argument("--text", required=True)
    ap.add_argument("--reply-to")
    a = ap.parse_args()
    mid = post(a.text, image_url=a.image_url, reply_to_id=a.reply_to)
    print("published media id:", mid)
