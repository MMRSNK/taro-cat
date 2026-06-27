"""Generate forecast text via OpenAI from drawn cards + (optional) question.

Uses the editable prompt at prompts/forecast_prompt.yaml.

CLI (real API call — costs credits):
    python tools/generate_forecast.py "твоє питання"
"""
import sys

from config import load_prompt, require, settings
from draw_cards import draw, format_cards


def generate(cards, question="", theme=None):
    """Return forecast text. `cards` is the list from draw_cards.draw()."""
    require("OPENAI_API_KEY")
    from openai import OpenAI

    theme = theme or settings.DAILY_THEME
    prompt = load_prompt()

    fill = {
        "theme": theme,
        "question": question or "(немає — загальний прогноз)",
        "cards": format_cards(cards),
        "lang": settings.lang_name,
    }
    system = prompt["system"].format(**fill)
    user = prompt["user_template"].format(**fill)

    model = settings.OPENAI_MODEL or prompt.get("model", "gpt-4o-mini")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=model,
        temperature=float(prompt.get("temperature", 0.9)),
        max_tokens=int(prompt.get("max_tokens", 500)),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = resp.choices[0].message.content.strip()

    from logsink import log_block
    log_block("FORECAST", model=model, theme=theme,
              question=(question or "(none)"), prompt=user, response=text)
    return text


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else ""
    cards = draw(3)
    print(format_cards(cards))
    print("\n--- forecast ---\n")
    print(generate(cards, question=q))
