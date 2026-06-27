# 🔮 Taro Bot — Threads tarot forecast bot

Posts a daily 3-card tarot forecast to Threads, and replies to anyone who @mentions
it with a question — each reply is a personalized 3-card reading (image + text).

Built on the **WAT framework** (Workflows / Agents / Tools):
- `workflows/` — markdown SOPs (setup + the two flows)
- `tools/` — deterministic Python that does the work
- `data/cards.json` — the full 78-card deck with Ukrainian meanings (from `karty-taro-instukcia.pdf`)
- `prompts/forecast_prompt.yaml` — the editable OpenAI prompt
- `cards/` — card scans (placeholders until you add real ones)

## How it works
```
draw 3 cards (random orientation)
   └─ OpenAI writes the forecast (prompt = prompts/forecast_prompt.yaml)
        └─ Pillow composes 3 scans into one image (reversed = rotated 180°)
             └─ catbox.moe hosts the image (public URL)
                  └─ Threads API publishes / replies
```
Two triggers: a **cron** (daily general post) and **mention polling** (replies).

## Setup
1. `pip install -r requirements.txt` (or use Docker).
2. `cp .env.example .env` and fill it in:
   - OpenAI key → already have one.
   - Threads creds → `workflows/setup_threads_api.md`
   - Image host → `workflows/setup_image_host.md` (default catbox.moe needs nothing)
3. Generate placeholder cards (optional; auto for tests):
   `python tools/make_placeholder_cards.py`
4. (Later) add real scans → `workflows/add_card_scans.md`

## Run

Local:
```bash
python tools/run_bot.py                 # scheduler (daily post + mention polling)
python tools/run_bot.py --post-now      # post one daily forecast now
python tools/run_bot.py --reply-once    # answer pending mentions now
python tools/run_bot.py --post-now --offline   # smoke test, no paid APIs
```

Docker:
```bash
docker compose up --build -d            # run the bot
docker compose logs -f                  # watch
docker compose run --rm bot python tools/run_bot.py --post-now --dry-run
```

## Config knobs (`.env`)
`POST_CRON` (daily schedule) · `MENTION_POLL_MINUTES` · `REVERSED_PROB` · `OPENAI_MODEL` ·
`FORECAST_LANG` · `TZ`. Prompt tone/length/params live in `prompts/forecast_prompt.yaml`.

## Notes
- Threads caps posts at 500 chars; the forecast is clamped to fit.
- Secrets live only in `.env` (gitignored). Never commit `.env`.
- Design spec: `docs/superpowers/specs/2026-06-27-threads-tarot-bot-design.md`.
