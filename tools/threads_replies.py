"""Read replies left UNDER the bot's own Threads posts.

Unlike `/me/mentions` (which only surfaces mentions from app testers until the
app has advanced access + business verification), `GET /{post_id}/replies` reads
comments under the bot's OWN posts for ANY user — including non-testers — on
standard access. Verified live 2026-06-28. This is the bot's reply source when
mentions are unavailable.

Returns replies not yet processed (deduped via state.py), each with a cleaned
`question` — the same shape as `threads_mentions.new_mentions()`, so it is a
drop-in source for `run_bot.do_replies`.

Requires `threads_read_replies` (or `threads_manage_replies`) on the token.
Docs: https://developers.facebook.com/docs/threads/reply-management

CLI (real API call):  python tools/threads_replies.py
"""
import requests

from config import require, settings
from state import is_seen
# Reuse the mention helpers — same bot identity + text cleaning rules.
from threads_mentions import bot_handle, strip_mention

POST_FIELDS = "id,timestamp"
REPLY_FIELDS = "id,text,username,timestamp,permalink"
_MAX_REPLY_PAGES = 5  # bounded paging per post; newest-first is enough at poll cadence


def recent_own_posts(limit=None):
    """Return the bot's recent own posts (newest first): list of {id, timestamp}."""
    require("THREADS_ACCESS_TOKEN")
    limit = limit or settings.OWN_POSTS_LIMIT
    r = requests.get(
        f"{settings.THREADS_API_BASE}/me/threads",
        params={"fields": POST_FIELDS,
                "limit": limit,
                "access_token": settings.THREADS_ACCESS_TOKEN},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"fetch own posts failed [{r.status_code}]: {r.text}")
    return r.json().get("data", [])


def fetch_replies(post_id):
    """Return all top-level replies under one post (follows paging, bounded)."""
    require("THREADS_ACCESS_TOKEN")
    out = []
    url = f"{settings.THREADS_API_BASE}/{post_id}/replies"
    params = {"fields": REPLY_FIELDS,
              "access_token": settings.THREADS_ACCESS_TOKEN}
    for _ in range(_MAX_REPLY_PAGES):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(
                f"fetch replies for {post_id} failed [{r.status_code}]: {r.text}")
        body = r.json()
        out.extend(body.get("data", []))
        nxt = body.get("paging", {}).get("next")
        if not nxt:
            break
        url, params = nxt, None  # `next` is a full URL with token + cursor baked in
    return out


def new_replies():
    """Replies under the bot's recent posts we haven't processed, each with a
    cleaned `question`. Skips the bot's own replies and already-seen ids."""
    handle = bot_handle()
    out = []
    seen_ids = set()
    for post in recent_own_posts():
        pid = post.get("id")
        if not pid:
            continue
        for rep in fetch_replies(pid):
            rid = rep.get("id")
            if not rid or rid in seen_ids or is_seen(rid):
                continue
            if (rep.get("username") or "").lower() == handle:
                continue  # never answer ourselves
            seen_ids.add(rid)
            rep["question"] = strip_mention(rep.get("text", ""), handle=handle)
            rep["post_id"] = pid
            out.append(rep)
    return out


if __name__ == "__main__":
    for m in new_replies():
        print(m["id"], "|", m.get("username"), "|", m.get("question"))
