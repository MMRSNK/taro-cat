"""Poll the Threads API for new @mentions of the bot account.

Returns mentions not yet processed (deduped via state.py). The text of each
mention is treated as the user's tarot question.

Requires the `threads_manage_mentions` permission on the access token.
Docs: https://developers.facebook.com/docs/threads/mentions

CLI (real API call):  python tools/threads_mentions.py
"""
import re

import requests

from config import require, settings
from state import is_seen

MENTION_FIELDS = "id,text,username,permalink,timestamp"


def fetch_mentions(limit=25):
    """Return raw mention objects from the API (newest first)."""
    require("THREADS_ACCESS_TOKEN")
    r = requests.get(
        f"{settings.THREADS_API_BASE}/me/mentions",
        params={"fields": MENTION_FIELDS,
                "limit": limit,
                "access_token": settings.THREADS_ACCESS_TOKEN},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"fetch mentions failed [{r.status_code}]: {r.text}")
    return r.json().get("data", [])


_bot_handle = None


def bot_handle():
    """The bot's own @username (lowercased, cached). From THREADS_USERNAME if set,
    otherwise fetched once from the API."""
    global _bot_handle
    if _bot_handle is not None:
        return _bot_handle
    if settings.THREADS_USERNAME:
        _bot_handle = settings.THREADS_USERNAME.lstrip("@").lower()
        return _bot_handle
    try:
        r = requests.get(f"{settings.THREADS_API_BASE}/me",
                         params={"fields": "username",
                                 "access_token": settings.THREADS_ACCESS_TOKEN}, timeout=20)
        _bot_handle = (r.json().get("username") or "").lower()
    except Exception:
        _bot_handle = ""
    return _bot_handle


def strip_mention(text, handle=None):
    """Return only the text AFTER the bot's @tag. Everything before the tag —
    other words, other @handles, and the tag itself — is ignored.
    Falls back to the LAST @handle if the bot handle isn't found; if there's no
    tag at all, the whole text is used."""
    if not text:
        return ""
    handle = (handle or "").lstrip("@").lower()
    cut = -1
    if handle:
        i = text.lower().rfind("@" + handle)
        if i != -1:
            cut = i + len("@" + handle)
    if cut == -1:
        matches = list(re.finditer(r"@\w[\w.]*", text))
        if matches:
            cut = matches[-1].end()
    if cut != -1:
        text = text[cut:]
    text = re.sub(r"@\w[\w.]*", " ", text)        # drop any leftover @handles
    text = re.sub(r"\s+", " ", text)              # collapse whitespace
    # drop leading separators after the tag, keep trailing punctuation (e.g. "?")
    return text.strip().lstrip(" \t\n\r:,.!-—–").strip()


def new_mentions():
    """Mentions we haven't processed yet, each with a cleaned `question`."""
    handle = bot_handle()
    out = []
    for m in fetch_mentions():
        mid = m.get("id")
        if not mid or is_seen(mid):
            continue
        m["question"] = strip_mention(m.get("text", ""), handle=handle)
        out.append(m)
    return out


if __name__ == "__main__":
    for m in new_mentions():
        print(m["id"], "|", m.get("username"), "|", m.get("question"))
