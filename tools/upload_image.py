"""Publish the composed image at a public URL for Threads to fetch.

We self-host: the image is written into PUBLIC_DIR by the in-process static
server (tools/image_server.py) and served publicly via a Cloudflare Tunnel.
The public base URL is PUBLIC_IMAGE_BASE (e.g. https://img.s3nko.com).

CLI (path/prune smoke test):  python tools/upload_image.py path/to/image.png
"""
import sys

from config import settings


def upload(image_path):
    """Store the image in the public dir and return its public URL."""
    if not settings.PUBLIC_IMAGE_BASE:
        raise SystemExit(
            "PUBLIC_IMAGE_BASE is not set — cannot build a public image URL. "
            "Set it in .env (e.g. https://img.s3nko.com)."
        )
    from image_server import publish_file
    name = publish_file(image_path)
    return f"{settings.PUBLIC_IMAGE_BASE.rstrip('/')}/{name}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/upload_image.py <image_path>")
    print(upload(sys.argv[1]))
