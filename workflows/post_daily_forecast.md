# Workflow: Daily general forecast post

Objective: once per schedule, post a general tarot forecast ("загальний прогноз для
всіх на сьогодні") with a 3-card image to Threads.

## Inputs
- `data/cards.json` (deck + meanings)
- `cards/*.png` (scans or placeholders)
- `prompts/forecast_prompt.yaml` (the OpenAI prompt — edit to change tone)
- `.env` (OpenAI / Imgur / Threads creds, `POST_CRON`)

## Flow (implemented in `tools/run_bot.py:do_daily`)
1. `draw_cards.draw(3)` — 3 unique cards, each random orientation (`REVERSED_PROB`).
2. `generate_forecast.generate(...)` — OpenAI writes the forecast (theme = general, no question).
3. `compose_image.compose(...)` — render 3 cards (reversed rotated 180°) + title into a PNG.
4. `upload_imgur.upload(...)` — get public image URL.
5. `threads_post.post(...)` — create image container, wait for processing, publish.

## Schedule
- Controlled by `POST_CRON` (5-field cron) and `TZ` in `.env`. Default `0 9 * * *` = 09:00 daily.
- The long-running `run_bot.py` (Docker `CMD`) registers this as an APScheduler cron job.

## Manual run / test
```bash
python tools/run_bot.py --post-now              # full: OpenAI + Imgur + Threads
python tools/run_bot.py --post-now --dry-run    # build image + text, do NOT post
python tools/run_bot.py --post-now --offline    # no paid APIs (stub text, just image)
```

## Edge cases / learnings
- Forecast clamped to 500 chars (Threads limit) by `threads_post.clamp_text`.
- If a card scan is missing, `compose_image` draws a placeholder tile (pipeline still works).
- Job errors are caught and logged; the scheduler keeps running.
