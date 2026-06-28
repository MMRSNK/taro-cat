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
import html
import re
import sys

import requests

from config import settings

# Threads serves OpenGraph tags (incl. the post text) to link-preview crawlers.
# Spoofing that UA lets us read ANY public post's text with a plain GET — no
# token, no login — which the Graph API won't do for other users' posts.
_OG_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
_OG_RE = re.compile(
    r'property=["\']og:description["\']\s+content=["\']([^"\']*)["\']', re.I)

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


def scrape_post_text(shortcode):
    """Read a public post's text via its OpenGraph og:description tag (no token).
    Works for ANY public post, including other users'. Returns '' on any failure
    or if og:description is missing. Note: very long posts may be truncated by OG.
    """
    try:
        r = requests.get(
            f"https://www.threads.com/t/{shortcode}",
            headers={"User-Agent": _OG_UA, "Accept-Encoding": "gzip, deflate"},
            timeout=30,
        )
        if r.status_code != 200:
            return ""
        m = _OG_RE.search(r.text)
        return html.unescape(m.group(1)).strip() if m else ""
    except requests.RequestException:
        return ""


def resolve(url):
    """Full resolve: link -> {username, shortcode, post_id, text}.
    `text` is best-effort ('' if it couldn't be read). Tries the Graph API first
    (works for the bot's own posts), then falls back to scraping og:description
    (works for any public post — token-free)."""
    username, shortcode = parse_threads_url(url)
    post_id = shortcode_to_post_id(shortcode)
    info = fetch_post(post_id)
    text = (info.get("text") or "").strip()
    if not text:
        text = scrape_post_text(shortcode)
    return {
        "username": info.get("username") or username,
        "shortcode": shortcode,
        "post_id": post_id,
        "text": text,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/answer_url.py <threads-post-url>")
    u, sc = parse_threads_url(sys.argv[1])
    print("username :", u)
    print("shortcode:", sc)
    print("post_id  :", shortcode_to_post_id(sc))
