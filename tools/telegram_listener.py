"""Telegram command bridge: receive a reading request via private message and
hand it off to be answered. Request forms accepted:
  - a Threads post link  (the post's text becomes the reading's context)
  - `@nickname - question`  (the question text drives the reading; the image
    caption shows only @nickname, like the link flow)
  - `/post <question>`  (build a general Threads post for the question and offer
    Publish / Re-forecast / Cancel inline buttons — see run_bot)

Besides messages the bot also receives `callback_query` updates from those inline
buttons; poll_once dispatches both to the handler.

Only messages from `TELEGRAM_ALLOWED_USER_ID` are honored; anything else is
ignored. The bot polls `getUpdates` (no webhook), persisting the update offset in
state.json so a restart doesn't reprocess old messages.

The actual answering is done by a `handler(cmd, chat_id)` callback passed in by
run_bot (keeps Threads logic out of this transport module); `cmd` is one of the
dicts returned by `parse_commands`.

CLI (process pending Telegram messages once — real send/answer):
    python tools/telegram_listener.py
"""
import json
import re

import requests

from config import settings
from state import get_value, set_value

_OFFSET_KEY = "telegram_offset"
# Any Threads post link inside the message text (keeps scheme + query intact;
# resolve()/parse_threads_url pulls out the username + shortcode).
_LINK_RE = re.compile(r"https?://[^\s]*threads\.(?:net|com)/[^\s]+", re.I)
# `@nickname - question` (dash/em-dash/en-dash/colon separator). The nickname is
# the single token after @; everything after the separator is the question.
_CMD_RE = re.compile(r"^\s*@\s*(\S+?)\s*[-–—:]\s+(.+)$", re.S)
# `/post <question>` (optionally `/post@botname <question>`).
_POST_RE = re.compile(r"^\s*/post(?:@\S+)?\s+(.+)$", re.S | re.I)


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


def send_photo(chat_id, image_path, caption="", reply_markup=None):
    """Send a local image with a caption back to the Telegram user. Telegram caps
    captions at 1024 chars — overflow is sent as a follow-up text message.
    `reply_markup` (a dict, e.g. an inline keyboard) is JSON-encoded if given.
    Returns the sent photo's message_id, or None on failure."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return None
    cap, rest = caption[:1024], caption[1024:]
    data = {"chat_id": chat_id, "caption": cap}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        with open(image_path, "rb") as f:
            r = requests.post(_api("sendPhoto"), data=data,
                              files={"photo": f}, timeout=60)
        mid = (r.json().get("result") or {}).get("message_id")
        if rest.strip():
            send_message(chat_id, rest)
        return mid
    except (requests.RequestException, OSError, ValueError):
        # Fall back to text-only so the user still gets the reading.
        send_message(chat_id, caption)
        return None


def edit_reply_markup(chat_id, message_id, reply_markup=None):
    """Replace (or, with reply_markup=None, remove) the inline keyboard on an
    already-sent message. Best-effort."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    data = {"chat_id": chat_id, "message_id": message_id,
            "reply_markup": json.dumps(reply_markup or {"inline_keyboard": []})}
    try:
        requests.post(_api("editMessageReplyMarkup"), data=data, timeout=30)
    except requests.RequestException:
        pass


def edit_caption(chat_id, message_id, caption, reply_markup=None):
    """Replace the caption (and optionally the keyboard) of a photo message.
    Best-effort."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    data = {"chat_id": chat_id, "message_id": message_id, "caption": caption[:1024]}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(_api("editMessageCaption"), data=data, timeout=30)
    except requests.RequestException:
        pass


def answer_callback(callback_query_id, text=""):
    """Acknowledge a button press so Telegram stops the client-side spinner.
    `text`, if set, shows as a small toast to the user. Best-effort."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
    try:
        requests.post(_api("answerCallbackQuery"), data=data, timeout=30)
    except requests.RequestException:
        pass


def get_updates(offset, timeout=0):
    """Return new updates (>= offset). timeout=0 keeps it non-blocking for the
    scheduler poll."""
    r = requests.get(_api("getUpdates"),
                     params={"offset": offset, "timeout": timeout,
                             "allowed_updates": '["message","callback_query"]'},
                     timeout=timeout + 30)
    if r.status_code != 200:
        raise RuntimeError(f"getUpdates failed [{r.status_code}]: {r.text}")
    return r.json().get("result", [])


def _extract_links(text):
    return _LINK_RE.findall(text or "")


def parse_commands(text):
    """Parse a Telegram message into reading commands.
    - Threads link(s)        -> {"kind": "link", "url": ...}
    - `/post <question>`     -> {"kind": "post", "question": ...}
    - `@nickname - question` -> {"kind": "question", "username": ..., "question": ...}
    Links win if present. Returns [] when nothing is recognized."""
    text = text or ""
    links = _extract_links(text)
    if links:
        return [{"kind": "link", "url": u} for u in links]
    m = _POST_RE.match(text)
    if m:
        return [{"kind": "post", "question": m.group(1).strip()}]
    m = _CMD_RE.match(text)
    if m:
        return [{"kind": "question",
                 "username": m.group(1).lstrip("@"),
                 "question": m.group(2).strip()}]
    return []


_USAGE = ("Кинь посилання на пост Threads, «@нікнейм - питання», або "
          "«/post питання» (запощу в Threads) — зроблю розклад. 🐾")


def _allowed(from_id):
    allowed = settings.TELEGRAM_ALLOWED_USER_ID
    return (not allowed) or str(from_id) == str(allowed)


def poll_once(handler):
    """Process all pending Telegram updates once. For each allowed message, parse
    it into reading command(s); for each inline-button press, build a callback
    command. Calls handler(cmd, chat_id) for each. Advances + persists the offset
    so updates are processed exactly once. Returns the number of commands handled.

    Callback command shape:
      {"kind": "callback", "data": <button data>, "message_id": <int>,
       "callback_query_id": <str>}
    The handler is responsible for calling answer_callback(callback_query_id)."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return 0
    offset = int(get_value(_OFFSET_KEY, 0))
    handled = 0

    for upd in get_updates(offset):
        offset = max(offset, upd["update_id"] + 1)
        set_value(_OFFSET_KEY, offset)  # advance even on bad/ignored updates

        cbq = upd.get("callback_query")
        if cbq:
            from_id = (cbq.get("from") or {}).get("id", "")
            cmsg = cbq.get("message") or {}
            chat_id = (cmsg.get("chat") or {}).get("id")
            if not _allowed(from_id):
                answer_callback(cbq.get("id", ""))  # silently dismiss others
                continue
            handler({"kind": "callback", "data": cbq.get("data", ""),
                     "message_id": cmsg.get("message_id"),
                     "callback_query_id": cbq.get("id", "")}, chat_id)
            handled += 1
            continue

        msg = upd.get("message")
        if not msg:
            continue
        from_id = (msg.get("from") or {}).get("id", "")
        chat_id = (msg.get("chat") or {}).get("id")
        text = msg.get("text", "")

        # Allow-list: ignore everyone except the configured user (silently).
        if not _allowed(from_id):
            continue

        cmds = parse_commands(text)
        if not cmds:
            send_message(chat_id, _USAGE)
            continue
        for cmd in cmds:
            handler(cmd, chat_id)
            handled += 1
    return handled


if __name__ == "__main__":
    # Standalone smoke test: just echo received commands, don't answer.
    def _echo(cmd, chat_id):
        print("command from", chat_id, "->", cmd)
        if cmd.get("kind") == "callback":
            answer_callback(cmd["callback_query_id"], "ok")
        else:
            send_message(chat_id, f"Отримав: {cmd}")
    print("handled:", poll_once(_echo))
