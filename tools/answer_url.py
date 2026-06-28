"""Resolve a Threads post LINK into the data needed to reply to it.

Used by the manual `--answer-url` command (run_bot.py): the operator hands the
bot a link to any post and the bot replies under it with a reading.

A Threads URL looks like:
    https://www.threads.com/@myaufar/post/DaISqvNjiyS?xmt=...&slof=1
                              ^username        ^shortcode  ^junk (ignored)

The Threads/Instagram shortcode is a base64-ish encoding of the numeric post id;
we decode it back to that id so it can be used as `reply_to_id`. The post's text
is fetched best-effort (may be blocked for other users' posts) to use as the
reading's context.

CLI (decode only, no API):  python tools/answer_url.py "<link>"
"""
import re
import sys

import requests

from config import settings

# Instagram/Threads shortcode alphabet (URL-safe base64, standard order).
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_IDX = {c: i for i, c in enumerate(_ALPHABET)}

# threads.net or threads.com, optional www, @user, /post/ or /t/ , then shortcode.
_URL_RE = re.compile(
    r"threads\.(?:net|com)/@([\w.]+)/(?:post|t)/([A-Za-z0-9_-]+)", re.IGNORECASE)


def parse_threads_url(url):
    """Return (username, shortcode) from a Threads post URL.
    Raises ValueError if the URL isn't a recognizable Threads post link."""
    m = _URL_RE.search(url or "")
    if not m:
        raise ValueError(
            "Не схоже на посилання на пост Threads "
            "(очікую .../@user/post/SHORTCODE): " + (url or ""))
    return m.group(1), m.group(2)


def shortcode_to_post_id(shortcode):
    """Decode a Threads/Instagram shortcode back to its numeric post id (string)."""
    n = 0
    for ch in shortcode:
        if ch not in _IDX:
            raise ValueError(f"Недопустимий символ у shortcode: {ch!r}")
        n = n * 64 + _IDX[ch]
    return str(n)


def fetch_post(post_id):
    """Best-effort {id, text, username} for a post. Returns {} on any failure
    (e.g. the API blocks reading another user's post) — never raises."""
    if not settings.THREADS_ACCESS_TOKEN:
        return {}
    try:
        r = requests.get(
            f"{settings.THREADS_API_BASE}/{post_id}",
            params={"fields": "id,text,username",
                    "access_token": settings.THREADS_ACCESS_TOKEN},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return {}


def resolve(url):
    """Full resolve: link -> {username, shortcode, post_id, text}.
    `text` is best-effort ('' if it couldn't be read)."""
    username, shortcode = parse_threads_url(url)
    post_id = shortcode_to_post_id(shortcode)
    info = fetch_post(post_id)
    return {
        "username": info.get("username") or username,
        "shortcode": shortcode,
        "post_id": post_id,
        "text": (info.get("text") or "").strip(),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/answer_url.py <threads-post-url>")
    u, sc = parse_threads_url(sys.argv[1])
    print("username :", u)
    print("shortcode:", sc)
    print("post_id  :", shortcode_to_post_id(sc))
