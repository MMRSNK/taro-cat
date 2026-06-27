"""Detect prompt-injection / abuse attempts in a mention question, and pick a
pre-canned reply when one is detected.

Tune the patterns below, or the messages in prompts/canned_replies.yaml.

CLI (quick test):  python tools/moderation.py "ignore all instructions"
"""
import random
import re
import sys

import yaml

from config import PROMPTS_DIR, ROOT

CANNED_FILE = PROMPTS_DIR / "canned_replies.yaml"

# Each pattern is matched case-insensitively against the question.
# Patterns require an action + an injection target to limit false positives.
_PATTERNS = [
    # English
    r"ignore\s+(the\s+|all\s+|any\s+)?(previous|prior|above|earlier|your)\s+(instruction|prompt|message|rule)",
    r"disregard\s+(the\s+|all\s+|your\s+)?(previous|above|prior|instruction|prompt|rule)",
    r"forget\s+(everything|all|the\s+previous|your\s+(instruction|prompt|rule))",
    r"(system|developer)\s+(prompt|message|instruction)",
    r"(reveal|show|print|repeat|leak)\s+(me\s+)?(your\s+|the\s+)?(system\s+)?(prompt|instruction)",
    r"you\s+are\s+(now|no\s+longer)\b",
    r"\bact\s+as\s+(a|an|if|the)\b",
    r"\bpretend\s+(to\s+be|you\s+are|that)\b",
    r"\bjailbreak\b|\bD\.?A\.?N\.?\b|do\s+anything\s+now",
    r"override\s+(the\s+)?(instruction|rule|system|prompt)",
    r"new\s+instructions?\s*[:\-]",
    # Ukrainian
    r"ігноруй\w*\s+(усі\s+|всі\s+|попередн|інструкц|правил)",
    r"забудь\w*\s+(усе|все|усі|всі|попередн|інструкц|правил|що\s+я)",
    r"систем\w*\s+(промпт|повідомлен|інструкц)",
    r"(покажи|виведи|повтори|розкрий)\s+(свій\s+|систем\w*\s+)?(промпт|інструкц)",
    r"(ти\s+тепер|ти\s+більше\s+не|уяви,?\s+що\s+ти|удай,?\s+що\s+ти|притворись|вдай,?\s+що\s+ти)\b",
    r"нові?\s+інструкц",
    # Russian
    r"игнорируй\w*\s+(все|всё|предыдущ|инструкц|правил)",
    r"забудь\w*\s+(все|всё|предыдущ|инструкц|правил)",
    r"системн\w*\s+(промпт|инструкц|сообщен)",
    r"(покажи|выведи|повтори)\s+(свой\s+|системн\w*\s+)?(промпт|инструкц)",
    r"(ты\s+теперь|ты\s+больше\s+не|притворись|представь,?\s+что\s+ты)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def is_injection(text):
    t = text or ""
    return any(c.search(t) for c in _COMPILED)


_FALLBACK = ("🔮 Карти відчувають нещирість. Постав справжнє питання — "
             "і отримаєш справжню відповідь.")


def pick_canned():
    """Return (text, image_path_or_None) for a detected injection."""
    try:
        data = yaml.safe_load(CANNED_FILE.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return _FALLBACK, None
    reps = [r for r in (data.get("replies") or []) if (r.get("text") or "").strip()]
    if not reps:
        return _FALLBACK, None
    r = random.choice(reps)
    img = r.get("image")
    img_path = (ROOT / img) if img else None
    if img_path and not img_path.exists():
        img_path = None
    return r["text"].strip(), img_path


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else ""
    print("injection:", is_injection(q))
    if is_injection(q):
        print("canned:", pick_canned())
