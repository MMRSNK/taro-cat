"""Tiny read-only static server for the composed forecast PNG.

Threads needs the image at a public URL. Instead of third-party hosts (all
unreliable for Meta's fetcher), we serve PUBLIC_DIR ourselves and expose it via
a Cloudflare Tunnel (img.s3nko.com -> localhost:IMAGE_SERVER_PORT).

Binds 0.0.0.0 so Docker's published port reaches it; the compose mapping
(127.0.0.1:PORT:PORT) restricts host exposure to localhost + the local
cloudflared.
"""
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config import PUBLIC_DIR, settings

_KEEP = 20            # newest N PNGs retained in PUBLIC_DIR
_server = None        # singleton guard
_lock = threading.Lock()


class _PngHandler(SimpleHTTPRequestHandler):
    """Serve only *.png from the served directory; everything else 404."""

    def list_directory(self, path):        # no directory listing
        self.send_error(404)
        return None

    def send_head(self):
        if not self.path.split("?", 1)[0].lower().endswith(".png"):
            self.send_error(404)
            return None
        return super().send_head()

    def log_message(self, *a):             # quiet; the bot logs its own lines
        pass


def publish_file(src_path):
    """Copy the PNG into PUBLIC_DIR, prune to the newest _KEEP, return its name."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(src_path)
    shutil.copyfile(src, PUBLIC_DIR / src.name)
    pngs = sorted(PUBLIC_DIR.glob("*.png"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for old in pngs[_KEEP:]:
        old.unlink(missing_ok=True)
    return src.name


def start_background():
    """Start the static server on a daemon thread once. Idempotent."""
    global _server
    with _lock:
        if _server is not None:
            return _server
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        handler = partial(_PngHandler, directory=str(PUBLIC_DIR))
        _server = ThreadingHTTPServer(("0.0.0.0", settings.IMAGE_SERVER_PORT),
                                      handler)
        threading.Thread(target=_server.serve_forever,
                         name="image-server", daemon=True).start()
        return _server
