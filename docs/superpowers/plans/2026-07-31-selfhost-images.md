# Self-host forecast images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the composed forecast PNG from an in-process static server on senko exposed via a dedicated Cloudflare Tunnel (img.s3nko.com), dropping all third-party image hosts; on publish failure send a Telegram alert instead of retrying.

**Architecture:** `run_bot` starts a read-only `ThreadingHTTPServer` on `0.0.0.0:8091` serving `.tmp/public/`. `upload()` copies the PNG there and returns `https://img.s3nko.com/<name>.png`. Docker publishes `127.0.0.1:8091:8091`; a host-mode `cloudflared` routes the Cloudflare edge to it. No host fallback/rotation; failures raise and callers alert the operator over Telegram.

**Tech Stack:** Python 3.12 stdlib (`http.server`, `threading`, `shutil`), requests, APScheduler, Docker Compose, Cloudflare Tunnel.

## Global Constraints

- Python 3.12 (Docker base `python:3.12-slim`).
- Server binds `0.0.0.0` **inside the container**; host exposure limited to `127.0.0.1` by the compose port mapping.
- No new pip dependencies (stdlib only for the server).
- No retry/fallback on upload or publish. The only retry that stays is `threads_post._post_retry`'s Threads-API transient-5xx backoff (unrelated to hosts).
- Tests live in `tests/` (new dir); run with `python -m pytest`. Import modules from `tools/` via `sys.path` insert in `tests/conftest.py`.
- Public base URL from `settings.PUBLIC_IMAGE_BASE`; port from `settings.IMAGE_SERVER_PORT` (default 8091). Public dir = `config.PUBLIC_DIR` = `.tmp/public/`.

---

### Task 1: Config + image server module

**Files:**
- Modify: `tools/config.py` (add `PUBLIC_DIR`, `PUBLIC_IMAGE_BASE`, `IMAGE_SERVER_PORT`; remove `IMAGE_HOST`, `IMGUR_CLIENT_ID`)
- Create: `tools/image_server.py`
- Create: `tests/conftest.py`
- Create: `tests/test_image_server.py`

**Interfaces:**
- Produces: `image_server.publish_file(src_path) -> str` (stored basename), `image_server.start_background() -> ThreadingHTTPServer` (idempotent). `config.PUBLIC_DIR: Path`, `settings.PUBLIC_IMAGE_BASE: str|None`, `settings.IMAGE_SERVER_PORT: int`.

- [ ] **Step 1: conftest for test imports**

Create `tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
```

- [ ] **Step 2: config edits**

In `tools/config.py`, add near the other path constants (after `PROMPT_FILE`):
```python
PUBLIC_DIR = TMP_DIR / "public"
```
In `class Settings`, replace the image-hosting block:
```python
    # Image hosting (catbox | tmpfiles | imgur)
    IMAGE_HOST = _get("IMAGE_HOST", "catbox")
    IMGUR_CLIENT_ID = _get("IMGUR_CLIENT_ID")  # only if IMAGE_HOST=imgur
```
with:
```python
    # Self-hosted image serving. The composed PNG is written to PUBLIC_DIR and
    # served by tools/image_server.py, exposed publicly via a Cloudflare Tunnel.
    PUBLIC_IMAGE_BASE = _get("PUBLIC_IMAGE_BASE")       # e.g. https://img.s3nko.com
    IMAGE_SERVER_PORT = int(_get("IMAGE_SERVER_PORT", "8091"))
```

- [ ] **Step 3: Write failing tests**

Create `tests/test_image_server.py`:
```python
import io
import urllib.request

import config
import image_server


def _mkpng(tmp_path, name):
    # 1x1 PNG bytes
    data = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000d49444154789c6360000002000100ffff0300000600"
        "05023d0a0a0000000049454e44ae426082")
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_publish_file_stores_and_prunes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "_KEEP", 3)
    names = []
    for i in range(5):
        src = _mkpng(tmp_path, f"f{i}.png")
        names.append(image_server.publish_file(str(src)))
    remaining = sorted(p.name for p in (tmp_path / "public").glob("*.png"))
    assert names[-1] == "f4.png"
    assert len(remaining) == 3               # pruned to newest _KEEP
    assert "f4.png" in remaining and "f0.png" not in remaining


def test_server_serves_png_and_404(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server.settings, "IMAGE_SERVER_PORT", 8199)
    _mkpng(tmp_path, "x.png")
    image_server.publish_file(str(tmp_path / "x.png"))
    image_server.start_background()
    with urllib.request.urlopen("http://127.0.0.1:8199/x.png", timeout=5) as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "image/png"
    try:
        urllib.request.urlopen("http://127.0.0.1:8199/x.txt", timeout=5)
        assert False, "non-png should 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_start_background_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(image_server.settings, "IMAGE_SERVER_PORT", 8198)
    monkeypatch.setattr(config, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "PUBLIC_DIR", tmp_path / "public")
    a = image_server.start_background()
    b = image_server.start_background()
    assert a is b
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `python -m pytest tests/test_image_server.py -q`
Expected: FAIL (`ModuleNotFoundError: image_server` / attribute errors).

- [ ] **Step 5: Implement `tools/image_server.py`**

```python
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
```

Note: the test monkeypatches `image_server.PUBLIC_DIR`; `publish_file`/`start_background` reference the module-global `PUBLIC_DIR`, so patching it takes effect.

- [ ] **Step 6: Run tests, verify pass**

Run: `python -m pytest tests/test_image_server.py -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add tools/config.py tools/image_server.py tests/conftest.py tests/test_image_server.py
git commit -m "feat(image): self-hosted static PNG server + config"
```

---

### Task 2: Rewrite upload_image to self-host only

**Files:**
- Modify: `tools/upload_image.py` (full rewrite)
- Create: `tests/test_upload_image.py`

**Interfaces:**
- Consumes: `image_server.publish_file`, `settings.PUBLIC_IMAGE_BASE`.
- Produces: `upload_image.upload(image_path) -> str` (public URL). `host_order`, `upload_catbox`, etc. no longer exist.

- [ ] **Step 1: Write failing tests**

Create `tests/test_upload_image.py`:
```python
import pytest

import upload_image


def test_upload_builds_public_url(monkeypatch):
    monkeypatch.setattr(upload_image.settings, "PUBLIC_IMAGE_BASE",
                        "https://img.s3nko.com/")
    # upload() lazily imports image_server.publish_file — patch it there.
    import image_server
    monkeypatch.setattr(image_server, "publish_file", lambda p: "forecast_x.png")
    url = upload_image.upload("whatever.png")
    assert url == "https://img.s3nko.com/forecast_x.png"


def test_upload_requires_base(monkeypatch):
    monkeypatch.setattr(upload_image.settings, "PUBLIC_IMAGE_BASE", None)
    with pytest.raises(SystemExit):
        upload_image.upload("whatever.png")
```

- [ ] **Step 2: Run tests, verify fail**

Run: `python -m pytest tests/test_upload_image.py -q`
Expected: FAIL (old `upload` has different signature / providers).

- [ ] **Step 3: Rewrite `tools/upload_image.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_upload_image.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/upload_image.py tests/test_upload_image.py
git commit -m "refactor(upload): self-host only, drop all third-party hosts"
```

---

### Task 3: Simplify threads_post (remove host rotation)

**Files:**
- Modify: `tools/threads_post.py`

**Interfaces:**
- Produces: `create_container`/`post` raise plain `RuntimeError` on failure. `MediaFetchError`, `MediaTimeoutError`, `_MEDIA_HOST_FETCH_SUBCODES`, `_code`, and the `image_fallback` param are removed.

- [ ] **Step 1: Remove the fetch-subcode / rotation machinery**

Delete the block defining `_MEDIA_HOST_FETCH_SUBCODES`, `MediaFetchError`, `MediaTimeoutError` (lines around 39-58) and the `_code` helper. Change `_post_retry` signature back to `def _post_retry(url, data, what, attempts=4, base_delay=4):` and its tail to:
```python
    msg = f"{what} failed [{last.status_code}]: {last.text}"
    raise RuntimeError(msg)
```
Change `create_container`'s call back to:
```python
    r = _post_retry(f"{_base()}/threads", params, "create container")
```
(remove `image_fallback=bool(image_url)`).

- [ ] **Step 2: Verify import + no stale references**

Run:
```bash
python -c "import sys; sys.path.insert(0,'tools'); import threads_post; assert not hasattr(threads_post,'MediaFetchError'); print('ok')"
```
Expected: `ok`.

Run: `grep -rn "MediaFetchError\|MediaTimeoutError\|host_order\|_MEDIA_HOST_FETCH" tools/`
Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add tools/threads_post.py
git commit -m "refactor(threads): drop host-rotation, single-host publish"
```

---

### Task 4: run_bot — simple publish, operator alerts, server startup

**Files:**
- Modify: `tools/run_bot.py` (`publish` 74-111, `do_daily` 114-122, `handle_post_callback` msg ~312, add `notify_operator`, start server in `main`)

**Interfaces:**
- Consumes: `upload_image.upload`, `image_server.start_background`, `telegram_listener.send_message`, `settings.PUBLIC_IMAGE_BASE`, `settings.TELEGRAM_*`.
- Produces: `notify_operator(text) -> None`.

- [ ] **Step 1: Rewrite `publish` (remove host loop)**

Replace the body from line 88 (`# Upload + post...`) through line 111 with:
```python
    # Self-host the image and post. No fallback: on failure the caller alerts
    # the operator over Telegram (see do_daily / handle_post_callback).
    from upload_image import upload

    image_url = upload(image_path)
    log.info("image at %s", image_url)
    media_id = post(text, image_url=image_url, reply_to_id=reply_to_id)
    log.info("published to Threads -> media id %s", media_id)
    return media_id
```
And change the import line 81 from `from threads_post import post, MediaFetchError` to `from threads_post import post`.

- [ ] **Step 2: Add `notify_operator` and wire `do_daily`**

Add above `do_daily`:
```python
def notify_operator(text):
    """DM the operator over Telegram (best-effort; no-op if the bridge is off)."""
    if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ALLOWED_USER_ID):
        return
    try:
        from telegram_listener import send_message
        send_message(settings.TELEGRAM_ALLOWED_USER_ID, text)
    except Exception:
        log.exception("operator notify failed")
```
Change `do_daily`'s except block to:
```python
    except Exception as e:
        log.exception("daily forecast failed")
        notify_operator(f"⚠️ Збій завантаження посту (денний):\n{e}")
```

- [ ] **Step 3: Reword the /post failure message**

In `handle_post_callback`, the `except Exception as e:` under `action == "post"`, change:
```python
            send_message(chat_id, f"Не вдалося опублікувати: {e}")
```
to:
```python
            send_message(chat_id, f"⚠️ Збій завантаження посту:\n{e}")
```

- [ ] **Step 4: Start the image server in `main`**

After `a = ap.parse_args()` (line ~406), before the dispatch `if a.answer_url:`, insert:
```python
    if settings.PUBLIC_IMAGE_BASE and not a.offline:
        import image_server
        image_server.start_background()
        log.info("image server on :%d serving %s",
                 settings.IMAGE_SERVER_PORT, config.PUBLIC_DIR)
```
Ensure `config` is importable here — the file already does `from config import settings`; add `import config` at the top imports if not present.

- [ ] **Step 5: Smoke-test import + offline daily**

Run:
```bash
python -c "import sys; sys.path.insert(0,'tools'); import run_bot; assert hasattr(run_bot,'notify_operator'); print('ok')"
```
Expected: `ok`.

Run: `python tools/run_bot.py --post-now --offline`
Expected: builds forecast, logs `[skip-post]`, exits 0 (offline skips publish; no server started).

- [ ] **Step 6: Commit**

```bash
git add tools/run_bot.py
git commit -m "feat(bot): single-host publish, operator Telegram alert, image server boot"
```

---

### Task 5: Infra — compose service + env docs

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:** none (deploy config).

- [ ] **Step 1: Add port + cloudflared to `docker-compose.yml`**

Under the `bot` service, add:
```yaml
    ports:
      # Static image server (Cloudflare Tunnel -> img.s3nko.com -> here).
      - "127.0.0.1:8091:8091"
```
Add a sibling service:
```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: taro-cloudflared
    restart: unless-stopped
    network_mode: host          # bridged can't reach the CF edge :7844 on senko
    command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
    profiles: ["tunnel"]        # `docker compose --profile tunnel up -d` on senko
```

- [ ] **Step 2: Validate compose**

Run: `docker compose config >/dev/null && echo ok` (on a box with docker; on the dev Windows box this may be skipped — verify YAML by eye).
Expected: `ok` (or clean YAML).

- [ ] **Step 3: Update `.env.example`**

Replace the image-hosting section with:
```
# ── Image hosting (self-hosted via Cloudflare Tunnel) ───
# The composed forecast PNG is served by the bot's built-in static server and
# exposed publicly through a Cloudflare Tunnel. Threads fetches it from there.
PUBLIC_IMAGE_BASE=https://img.s3nko.com
IMAGE_SERVER_PORT=8091
# Token for the dedicated cloudflared tunnel (Cloudflare Zero Trust -> Tunnels).
CLOUDFLARE_TUNNEL_TOKEN=
```
Remove any `IMAGE_HOST` / `IMGUR_CLIENT_ID` lines.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore(deploy): cloudflared tunnel service + self-host image env"
```

---

### Task 6: Full test run + cleanup verification

**Files:** none (verification)

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Grep for dead references**

Run: `grep -rn "catbox\|tmpfiles\|litterbox\|imgur\|IMAGE_HOST\|host_order" tools/ .env.example`
Expected: no matches (or only historical comments intentionally kept — there should be none).

- [ ] **Step 3: Commit any residue**

If Step 2 found leftovers, fix and:
```bash
git add -A && git commit -m "chore: remove residual third-party host references"
```
