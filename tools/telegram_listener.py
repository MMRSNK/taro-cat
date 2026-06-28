"""Telegram command bridge: receive a Threads post link via private message and
hand it off to be answered.

Only messages from `TELEGRAM_ALLOWED_USER_ID` are honored; anything else is
ignored. The bot polls `getUpdates` (no webhook), persisting the update offset in
state.json so a restart doesn't reprocess old messages.

The actual answering is done by a `handler(url, chat_id)` callback passed in by
run_bot (keeps Threads logic out of this transport module).

CLI (process pending Telegram messages once — real send/answer):
    python tools/telegram_listener.py
"""
import re

import requests

from config import settings
from state import get_value, set_value

_OFFSET_KEY = "telegram_offset"
# Any Threads post link inside the message text (keeps scheme + query intact;
# resolve()/parse_threads_url pulls out the username + shortcode).
_LINK_RE = re.compile(r"https?://[^\s]*threads\.(?:net|com)/[^\s]+", re.I)


def _api(method):
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def send_message(chat_id, text):
    """Send a plain-text reply back to the Telegram user. Best-effort."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(_api("sendMessage"),
                      data={"chat_id": chat_id, "text": text,
                            "disable_web_page_preview": True},
                      timeout=30)
    except requests.RequestException:
        pass


def send_photo(chat_id, image_path, caption=""):
    """Send a local image with a caption back to the Telegram user. Telegram caps
    captions at 1024 chars — overflow is sent as a follow-up text message."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    cap, rest = caption[:1024], caption[1024:]
    try:
        with open(image_path, "rb") as f:
            requests.post(_api("sendPhoto"),
                          data={"chat_id": chat_id, "caption": cap},
                          files={"photo": f}, timeout=60)
        if rest.strip():
            send_message(chat_id, rest)
    except (requests.RequestException, OSError):
        # Fall back to text-only so the user still gets the reading.
        send_message(chat_id, caption)


def get_updates(offset, timeout=0):
    """Return new updates (>= offset). timeout=0 keeps it non-blocking for the
    scheduler poll."""
    r = requests.get(_api("getUpdates"),
                     params={"offset": offset, "timeout": timeout,
                             "allowed_updates": '["message"]'},
                     timeout=timeout + 30)
    if r.status_code != 200:
        raise RuntimeError(f"getUpdates failed [{r.status_code}]: {r.text}")
    return r.json().get("result", [])


def _extract_links(text):
    return _LINK_RE.findall(text or "")


def poll_once(handler):
    """Process all pending Telegram messages once. For each allowed message with
    a Threads link, call handler(url, chat_id). Advances + persists the offset so
    messages are processed exactly once. Returns the number of links handled."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return 0
    allowed = settings.TELEGRAM_ALLOWED_USER_ID
    offset = int(get_value(_OFFSET_KEY, 0))
    handled = 0

    for upd in get_updates(offset):
        offset = max(offset, upd["update_id"] + 1)
        set_value(_OFFSET_KEY, offset)  # advance even on bad/ignored msgs

        msg = upd.get("message")
        if not msg:
            continue
        from_id = str((msg.get("from") or {}).get("id", ""))
        chat_id = (msg.get("chat") or {}).get("id")
        text = msg.get("text", "")

        # Allow-list: ignore everyone except the configured user (silently).
        if allowed and from_id != str(allowed):
            continue

        links = _extract_links(text)
        if not links:
            send_message(chat_id, "Кинь посилання на пост Threads — відповім під ним. 🐾")
            continue
        for url in links:
            handler(url, chat_id)
            handled += 1
    return handled


if __name__ == "__main__":
    # Standalone smoke test: just echo received links, don't answer.
    def _echo(url, chat_id):
        print("link from", chat_id, "->", url)
        send_message(chat_id, f"Отримав: {url}")
    print("handled:", poll_once(_echo))
