# Design: answer replies under the bot's own posts (no Meta verification)

Date: 2026-06-28

## Goal

Let the tarot bot read and answer comments left **under its own Threads posts**,
without depending on `/me/mentions` (which needs App Review + Meta business
verification the user cannot obtain).

## Background / why this works

- `/me/mentions` only surfaces mentions from **app testers** until the app gets
  advanced access (App Review + business verification). Blocked for the user.
- **Proven live (2026-06-28):** `GET /{post_id}/replies` returns comments under
  the bot's own posts for **any** user — including non-testers — on standard
  access, no review. Proof: `mamrosenko` was removed as a tester; `/me/mentions`
  dropped to count 0 (mention gone) while the same account's reply still showed
  in `/{post_id}/replies` (200, count 1). Scope `threads_read_replies` is already
  on the token.

This is the first step. Reading standalone `@mentions` from anywhere (cookie
replay scrape on the postmarketOS server) is **deferred** — out of scope here.

## Approach

Keep the entire reply pipeline (`draw → forecast → compose → upload → reply →
mark_seen`, plus moderation/canned screening) unchanged. Swap only the **source**
of incoming questions: instead of `/me/mentions`, read replies under the bot's
recent own posts. The new source returns items in the exact same shape the
existing loop already consumes.

## Components & interfaces

### New: `tools/threads_replies.py` (mirror of `threads_mentions.py`)

- `recent_own_posts(limit=N)` → `GET /me/threads?fields=id,timestamp&limit=N`.
  Returns the bot's recent post ids (the daily forecasts).
- `fetch_replies(post_id)` → `GET /{post_id}/replies` with fields
  `id,text,username,timestamp,permalink`. Follows `paging.next` for a small,
  bounded number of pages (newest first is enough at poll cadence).
- `new_replies()` → gather replies across recent posts, then drop:
  - replies authored by the bot itself (`username == bot_handle()`),
  - replies already in `state.seen_mentions` (`is_seen`),
  and attach `question` (reply text, cleaned via the existing `strip_mention`
  helper so any leading `@handle` is removed). Returns a list of dicts shaped
  exactly like `threads_mentions.new_mentions()`:
  `{id, username, question, permalink, ...}`.

Reuse `bot_handle()` and `strip_mention()` from `threads_mentions.py` (import,
don't duplicate).

### Changed: `tools/run_bot.py`

- New config `REPLY_SOURCES` (comma list, default `post_replies`). `do_replies`
  picks the source function(s) by name, merges + dedups results, then runs the
  **existing** per-item loop untouched.
  - `post_replies` → `threads_replies.new_replies`
  - `mentions` → `threads_mentions.new_mentions` (kept for testers / future)
- Factor the source selection into a tiny helper; the moderation → forecast →
  reply → mark_seen body stays as-is.

### Changed: `tools/config.py`

- Add `REPLY_SOURCES = _get("REPLY_SOURCES", "post_replies")`.
- Add `OWN_POSTS_LIMIT = int(_get("OWN_POSTS_LIMIT", "5"))` — how many recent
  posts to scan for replies.

### State (`state.py`) — unchanged

`seen_mentions` already stores opaque ids; reply ids slot in directly. No schema
change.

## Data flow

```
poll tick
  → recent_own_posts()                     # GET /me/threads
  → for each post: fetch_replies(post_id)  # GET /{id}/replies
  → filter (not self, not seen) + clean text
  → existing loop: screen → (canned | draw→forecast→compose→upload→post reply)
  → mark_seen(reply_id)
```

Reply is posted with the existing `threads_post.post(..., reply_to_id=reply_id)`,
which already works (no media-id decoding needed — the reply id comes straight
from the API).

## Edge cases

- **First-run backlog:** on the very first run, existing old replies must NOT all
  get answered (spam). Behavior: a one-time `python tools/run_bot.py --seed-seen`
  marks all currently-visible replies as seen without answering, so only replies
  arriving *after* seeding get answered. (Single mechanism — no separate config.)
- **Empty reply text** (image/emoji only, e.g. `🔮🐾`) → falls back to the
  general "Загальний розклад на сьогодні", same as empty mentions today.
- **Self-replies:** the bot answers nested (`reply_to_id`=user reply), so its
  answers are not top-level replies to the post and won't reappear; the
  `username == bot_handle` filter is a belt-and-suspenders guard.
- **Pagination / volume:** bounded page-follow; few posts × few replies per tick
  is light on rate limits.
- **`/replies` permission regression:** if a future token lacks
  `threads_read_replies`, `fetch_replies` raises a clear error (like
  `fetch_mentions`), logged and skipped by `do_replies`.

## Testing plan

- Unit/offline: `new_replies()` shape + filtering (self, seen, empty text) with a
  stubbed `fetch_replies`. `strip_mention` reuse verified.
- Live smoke (free GET): `python tools/threads_replies.py` lists current new
  replies (the `mamrosenko` `🔮🐾` comment should appear as one item).
- Dry-run end-to-end: `python tools/run_bot.py --reply-once --dry-run` builds a
  reply to that comment without posting.
- Real: one live `--reply-once` answering the test comment, confirm `mark_seen`
  prevents a second answer on the next tick.

## Out of scope (deferred)

- Reading standalone `@mentions` from anywhere via cookie-replay scraping on the
  postmarketOS server. Revisit after this ships.
