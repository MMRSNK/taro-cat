"""Draw N unique random tarot cards, each with a random orientation.

Pure / deterministic-ish (randomness only). No network, no paid APIs.

CLI:  python tools/draw_cards.py [N]
"""
import json
import random
import sys

from config import CARDS_JSON, settings


def load_deck():
    with open(CARDS_JSON, encoding="utf-8") as f:
        return json.load(f)


def draw(n=3, reversed_prob=None, rng=None):
    """Return a list of n drawn cards. Each is the card dict plus:
        reversed: bool
        orientation: 'пряма' | 'перевернута'
        meaning: the meaning text for the current orientation
    """
    if reversed_prob is None:
        reversed_prob = settings.REVERSED_PROB
    rng = rng or random

    deck = load_deck()
    if n > len(deck):
        raise ValueError(f"cannot draw {n} from {len(deck)} cards")

    picked = rng.sample(deck, n)
    result = []
    for card in picked:
        is_rev = rng.random() < reversed_prob
        c = dict(card)
        c["reversed"] = is_rev
        c["orientation"] = "перевернута" if is_rev else "пряма"
        c["meaning"] = card["reversed"] if is_rev else card["upright"]
        result.append(c)
    return result


def format_cards(cards):
    """Render drawn cards as a numbered text block for the OpenAI prompt."""
    lines = []
    for i, c in enumerate(cards, 1):
        arrow = "↓" if c["reversed"] else "↑"
        lines.append(f"{i}. {c['name_uk']} ({c['orientation']} {arrow}): {c['meaning']}")
    return "\n".join(lines)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    cards = draw(n)
    print(format_cards(cards))
