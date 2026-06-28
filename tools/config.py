"""Central config + shared paths. Loads .env and the prompt yaml once."""
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Make console output UTF-8 safe (Windows consoles default to cp1251/cp437 and
# choke on Cyrillic / ↑↓ glyphs). No-op where already UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent

# Paths
DATA_DIR = ROOT / "data"
CARDS_DIR = ROOT / "cards"
TMP_DIR = ROOT / ".tmp"
PROMPTS_DIR = ROOT / "prompts"
CARDS_JSON = DATA_DIR / "cards.json"
STATE_JSON = DATA_DIR / "state.json"
PROMPT_FILE = PROMPTS_DIR / "forecast_prompt.yaml"

# Load .env (no-op in Docker where vars come from env_file, but handy locally).
load_dotenv(ROOT / ".env")

LANG_NAMES = {"uk": "українська", "en": "English", "ru": "русский"}


def _get(name, default=None):
    v = os.getenv(name)
    return v if v not in (None, "") else default


class Settings:
    # OpenAI
    OPENAI_API_KEY = _get("OPENAI_API_KEY")
    OPENAI_MODEL = _get("OPENAI_MODEL")  # overrides yaml `model` if set

    # Threads
    THREADS_USER_ID = _get("THREADS_USER_ID")
    THREADS_ACCESS_TOKEN = _get("THREADS_ACCESS_TOKEN")
    THREADS_USERNAME = _get("THREADS_USERNAME")  # bot handle, e.g. myaufar (optional)
    THREADS_API_BASE = _get("THREADS_API_BASE", "https://graph.threads.net/v1.0")

    # Image hosting (catbox | tmpfiles | imgur)
    IMAGE_HOST = _get("IMAGE_HOST", "catbox")
    IMGUR_CLIENT_ID = _get("IMGUR_CLIENT_ID")  # only if IMAGE_HOST=imgur

    # Behavior
    POST_CRON = _get("POST_CRON", "0 9 * * *")
    MENTION_POLL_MINUTES = int(_get("MENTION_POLL_MINUTES", "5"))
    # Where reply questions come from (comma list): post_replies | mentions.
    # post_replies = comments under the bot's own posts (works for any user,
    # no verification). mentions = /me/mentions (testers only until App Review).
    REPLY_SOURCES = _get("REPLY_SOURCES", "post_replies")
    OWN_POSTS_LIMIT = int(_get("OWN_POSTS_LIMIT", "5"))  # recent posts scanned for replies
    REVERSED_PROB = float(_get("REVERSED_PROB", "0.5"))
    FORECAST_LANG = _get("FORECAST_LANG", "uk")
    TZ = _get("TZ", "Europe/Kyiv")

    DAILY_THEME = "загальний прогноз для всіх на сьогодні"

    @property
    def lang_name(self):
        return LANG_NAMES.get(self.FORECAST_LANG, self.FORECAST_LANG)


settings = Settings()


def load_prompt():
    """Return the parsed prompt yaml dict."""
    with open(PROMPT_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def require(*names):
    """Raise a clear error if any required env var is missing."""
    missing = [n for n in names if not getattr(settings, n, None)]
    if missing:
        raise SystemExit(
            "Missing required config: " + ", ".join(missing)
            + "\nSet them in .env (see .env.example and workflows/)."
        )
