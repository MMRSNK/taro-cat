# Self-host forecast images via Cloudflare Tunnel

**Date:** 2026-07-31
**Status:** approved (design)

## Problem

Threads' Graph API accepts only a public `image_url` (no direct byte upload,
no resumable upload for image containers — confirmed 2026-07). We composed the
forecast PNG locally and relied on free third-party image hosts to give Meta a
public URL. Every host has become unreliable for Meta's server-side fetcher:

- **catbox** — Meta's fetch times out / errors (2207003, generic 500 code 1);
  catbox is effectively blocked for Meta.
- **tmpfiles** — Meta fetches the `/dl/` URL but gets a non-image →
  2207083 "image format is not supported".
- **litterbox / imgur / 0x0** — either same family as catbox, need creds, or
  dead (0x0 disabled uploads).

Result: `/post` and the daily post fail on image publish, sometimes silently
(daily post swallows the exception into the log).

## Goal

Stop depending on third-party hosts entirely. Serve the composed PNG from our
own infrastructure — the **senko** home server (postmarketOS phone) already
runs taro-bot in Docker and a working Cloudflare Tunnel (pattern proven by
`healthbot.s3nko.com`). Meta then fetches the image straight from the Cloudflare
edge: fast, correct `Content-Type`, TLS, zero external dependency.

On any publish failure: **no retry, no fallback** — send a Telegram alert to the
operator with the error, and do not publish.

## Non-goals

- No multi-host fallback / rotation. Removed entirely.
- No retry of the upload/publish on failure (see "Retry policy" for the one
  narrow exception that stays: Threads-API transient 5xx).
- No changes to the reading/forecast logic, moderation, or Telegram command
  parsing.

## Architecture

```
compose PNG  ──►  upload_selfhost()  ──►  writes .tmp/public/<name>.png
                                          returns https://img.s3nko.com/<name>.png
                                                       │
run_bot boot ──► image_server thread (0.0.0.0:8091, serves .tmp/public/, .png only)
                                                       │
              docker publishes 127.0.0.1:8091:8091 on senko host
                                                       │
              cloudflared (network_mode: host) ──► Cloudflare edge
                                                       │
Threads create_container(image_url=https://img.s3nko.com/<name>.png)
              Meta fetches from edge ──► publish
```

### Components

**`tools/image_server.py`** (new)
- `ThreadingHTTPServer` bound to `0.0.0.0:<IMAGE_SERVER_PORT>` (default 8091).
  Binds `0.0.0.0` **inside the container** so Docker's published port reaches it;
  host exposure is restricted to `127.0.0.1` by the compose port mapping, so only
  the local cloudflared can reach it.
- Serves a single directory `.tmp/public/`, read-only. Only `*.png`. No
  directory listing. Unknown/other paths → 404. `Content-Type: image/png`.
- `start_background()` — idempotent; starts the server on a daemon thread and
  returns immediately. Safe to call more than once (singleton guard).
- `publish_file(src_path) -> name` — copy the composed PNG into `.tmp/public/`
  under its basename (already timestamped, e.g. `forecast_YYYYMMDD_HHMMSS.png`),
  prune the directory to the newest 20 files by mtime, return the stored name.

**`tools/upload_image.py`** (gutted)
- Delete `upload_catbox`, `upload_tmpfiles`, `upload_litterbox`, `upload_imgur`,
  `_PROVIDERS`, `host_order`, `_UA`, and the catbox retry logic.
- New single path:
  ```python
  def upload(image_path):
      from image_server import publish_file
      name = publish_file(image_path)
      base = require_base()  # settings.PUBLIC_IMAGE_BASE, error if unset
      return f"{base.rstrip('/')}/{name}"
  ```
- CLI (`__main__`) prints the resulting URL (won't be publicly reachable unless
  run on senko, but fine for a smoke test of the path/prune logic).

**`tools/run_bot.py`**
- `publish()` loses the host-rotation loop. Body becomes: if no image →
  text-only post; else `image_url = upload(image_path)` then
  `post(text, image_url=image_url, reply_to_id=...)`. No try/except around hosts.
- New `notify_operator(text)`:
  ```python
  def notify_operator(text):
      if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ALLOWED_USER_ID):
          return
      try:
          from telegram_listener import send_message
          send_message(settings.TELEGRAM_ALLOWED_USER_ID, text)
      except Exception:
          log.exception("operator notify failed")
  ```
- `do_daily` except block: `log.exception(...)` **and**
  `notify_operator(f"⚠️ Збій публікації денного посту:\n{e}")`.
- `handle_post_callback` "post" failure: keep the existing in-chat
  `send_message(chat_id, ...)` but reword to the agreed
  `f"⚠️ Збій завантаження посту:\n{e}"`. (chat_id here is already the operator —
  the only allowed user — so this is the alert; no separate notify needed.)
- Start the image server at process start: in `main()` (covers both the
  long-running scheduler and one-shot `--daily`/`--answer-url` publishes), call
  `image_server.start_background()` guarded by `settings.PUBLIC_IMAGE_BASE` being
  set. For a one-shot publish the server only needs to live while `publish()`
  blocks (Meta fetches synchronously during `create_container` / `wait_ready`),
  which it does.

**`tools/threads_post.py`** (simplify)
- Remove the host-rotation additions from commit `9d27404`: `_code`,
  `image_fallback` param, and the `MediaFetchError` promotion of generic
  500/code-1. With a single host there is nothing to rotate to.
- `_MEDIA_HOST_FETCH_SUBCODES` / `MediaFetchError` / `MediaTimeoutError` can be
  deleted too (no consumer left); `create_container` failures surface as plain
  `RuntimeError`, which the callers already catch and turn into alerts.

**`tools/config.py`**
- Remove `IMAGE_HOST`, `IMGUR_CLIENT_ID`.
- Add `PUBLIC_IMAGE_BASE = _get("PUBLIC_IMAGE_BASE")` (e.g.
  `https://img.s3nko.com`) and `IMAGE_SERVER_PORT = int(_get("IMAGE_SERVER_PORT", "8091"))`.
- Add path constant `PUBLIC_DIR = TMP_DIR / "public"`.

### Retry policy

- **Upload / host:** none. One shot; fail → alert.
- **Threads API transient 5xx:** the existing `_post_retry` backoff (Threads
  flags `is_transient` / code 2 / HTTP ≥500 from its *own* backend, unrelated to
  the image host) **stays**. It recovers genuine Meta blips and prevents false
  alerts. It is not the flaky-host retry the user asked to remove.
  → **Flagged for user veto in spec review.** If the user wants literally zero
  retries anywhere, drop `_post_retry`'s loop to a single attempt.

## Infrastructure (senko + Cloudflare)

**`docker-compose.yml`**
- taro-bot service: add `ports: ["127.0.0.1:8091:8091"]`.
- New `cloudflared` service, mirroring the health-bot pattern:
  ```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: taro-cloudflared
    restart: unless-stopped
    network_mode: host          # required — bridged can't reach CF edge :7844 on senko
    command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
    profiles: ["tunnel"]        # only starts on senko: `docker compose --profile tunnel up -d`
  ```
  Host-mode so it can reach both the CF edge and the host-published
  `localhost:8091`.

**Cloudflare Zero Trust (manual, operator action)**
1. Create a new tunnel (dedicated to taro-bot).
2. Copy its token → senko `.env` as `CLOUDFLARE_TUNNEL_TOKEN`.
3. Add a public hostname: `img.s3nko.com` → service `http://localhost:8091`.

**senko `.env` additions**
```
PUBLIC_IMAGE_BASE=https://img.s3nko.com
IMAGE_SERVER_PORT=8091
CLOUDFLARE_TUNNEL_TOKEN=<from step 2>
```
Remove `IMAGE_HOST` / `IMGUR_CLIENT_ID`.

**`.env.example`** — update the image-hosting section to document
`PUBLIC_IMAGE_BASE`, `IMAGE_SERVER_PORT`, `CLOUDFLARE_TUNNEL_TOKEN`; drop the
catbox/tmpfiles/imgur notes.

## Error handling / flow

- Image server fails to bind at boot → log error; publishes will then fail on the
  unreachable URL and alert. (Acceptable; misconfig is loud.)
- Tunnel down / DNS not set → Meta can't fetch → `create_container` errors →
  caller catches → `notify_operator` / in-chat alert. No publish, no retry.
- One-shot `--daily` on the dev box (no tunnel) → publish will fail and alert;
  expected. Real publishing happens on senko.

## Testing

- **Unit (offline, dev box):**
  - `image_server.publish_file` copies into `.tmp/public/`, returns basename,
    prunes to newest 20 (create 25 dummy files, assert 20 remain, newest kept).
  - `upload_image.upload` returns `f"{PUBLIC_IMAGE_BASE}/<name>.png"`; raises a
    clear error when `PUBLIC_IMAGE_BASE` unset.
  - `image_server` serves a written PNG over `127.0.0.1:<port>` with
    `Content-Type: image/png` and 200; a non-png / traversal path → 404;
    `start_background` is idempotent.
  - `notify_operator` no-ops when token/user unset (monkeypatch send_message).
- **Live (senko, after infra):**
  - `curl -I https://img.s3nko.com/<known>.png` → 200, `content-type: image/png`.
  - `/post` a test question → Publish → media id returned, image renders in-app.
  - Force-fail (temporarily point PUBLIC_IMAGE_BASE at a bad host) → daily/`/post`
    sends the Telegram alert with the error.

## Deploy

Code is baked into the image (not a volume) → rebuild required:
```
git pull
# edit .env: add PUBLIC_IMAGE_BASE, IMAGE_SERVER_PORT, CLOUDFLARE_TUNNEL_TOKEN; remove IMAGE_HOST/IMGUR_CLIENT_ID
docker compose --profile tunnel up -d --build
```
Verify: `docker compose logs -f cloudflared` shows the tunnel registered;
image server bind logged by the bot; `curl -I https://img.s3nko.com/...`.
