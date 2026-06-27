"""Append human-readable interaction logs to data/prompts.log.

Records what was sent to OpenAI (rendered prompt) and what came back, plus
injection events. The file can hold user questions, so it's gitignored.
"""
from datetime import datetime

from config import DATA_DIR

LOG = DATA_DIR / "prompts.log"


def log_block(title, **fields):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = [f"===== {title} @ {datetime.now().isoformat(timespec='seconds')} ====="]
    for k, v in fields.items():
        out.append(f"--- {k} ---")
        out.append(str(v).strip())
    out.append("")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
