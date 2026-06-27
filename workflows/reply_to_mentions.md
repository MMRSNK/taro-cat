# Workflow: Reply to @mentions with a personalized forecast

Objective: when someone @mentions the bot with a question, reply with a 3-card
forecast image + text answering that question.

## Inputs
- `.env` with `THREADS_*` (token needs `threads_manage_mentions` + `threads_manage_replies`)
- `MENTION_POLL_MINUTES` (poll interval)
- Same deck / prompt / hosting as the daily flow.

## Flow (implemented in `tools/run_bot.py:do_replies`)
1. `threads_mentions.new_mentions()` — GET `/me/mentions`, drop ids already in `data/state.json`.
2. For each new mention:
   - `strip_mention(text)` → the user's question (leading @handles removed).
   - `draw_cards.draw(3)` → 3 cards.
   - `generate_forecast.generate(question=...)` → forecast tied to the question.
   - `compose_image.compose(...)` → image.
   - `upload_imgur.upload(...)` → public URL.
   - `threads_post.post(text, image_url, reply_to_id=mention_id)` → reply.
   - `state.mark_seen(mention_id)` → never answer the same mention twice.

## Schedule
- APScheduler interval job every `MENTION_POLL_MINUTES` (default 5) inside `run_bot.py`.

## Manual run / test
```bash
python tools/threads_mentions.py                 # list new mentions (no reply)
python tools/run_bot.py --reply-once             # process pending mentions now
python tools/run_bot.py --reply-once --dry-run   # build replies but don't post
```

## Edge cases / learnings
- Dedupe is by mention id in `data/state.json` (persisted via the Docker `data/` volume).
  In `--dry-run`/`--offline` the id is **not** marked seen, so you can re-test.
- Empty question (just a tag, no text) → falls back to a general "розклад на сьогодні".
- One reply per mention per run; failures are logged and skipped, others continue.
- Mentions API requires the account to be approved + token to hold `threads_manage_mentions`.
