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


def strip_mention(text):
    """Return only the text AFTER the @tag. Anything before the tag (including
    other words and the bot handle itself) is ignored. If there is no tag, the
    whole text is used."""
    if not text:
        return ""
    matches = list(re.finditer(r"@\w[\w.]*", text))
    if matches:
        text = text[matches[-1].end():]
    # drop leading separators after the tag, keep trailing punctuation (e.g. "?")
    return text.strip().lstrip(" \t\n\r:,.!-—–").strip()


def new_mentions():
    """Mentions we haven't processed yet, each with a cleaned `question`."""
    out = []
    for m in fetch_mentions():
        mid = m.get("id")
        if not mid or is_seen(mid):
            continue
        m["question"] = strip_mention(m.get("text", ""))
        out.append(m)
    return out


if __name__ == "__main__":
    for m in new_mentions():
        print(m["id"], "|", m.get("username"), "|", m.get("question"))
