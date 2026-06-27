"""Tiny JSON state store (processed mention ids). Survives restarts via the
data/ volume.
"""
import json

from config import STATE_JSON

_MAX_SEEN = 1000


def _load():
    if STATE_JSON.exists():
        try:
            return json.loads(STATE_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"seen_mentions": []}


def _save(state):
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def is_seen(mention_id):
    return mention_id in _load().get("seen_mentions", [])


def mark_seen(mention_id):
    state = _load()
    seen = state.setdefault("seen_mentions", [])
    if mention_id not in seen:
        seen.append(mention_id)
        # keep bounded
        state["seen_mentions"] = seen[-_MAX_SEEN:]
        _save(state)
