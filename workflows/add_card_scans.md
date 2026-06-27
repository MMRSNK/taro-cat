# Workflow: Add the real card scans

The bot ships with generated placeholders so it runs immediately. Replace them with
real scans whenever you're ready — drop files into `cards/` using the exact names below.

## Rules
- **78 upright scans only.** The bot makes reversed cards by rotating 180° in code —
  do NOT scan or supply reversed images.
- Format: **PNG**, portrait orientation. Recommended ratio ~ 3:5 (e.g. 600×1000).
  Any size works (auto-resized to 360×600), but keep all cards consistent.
- File names must match `image` in `data/cards.json` exactly (lowercase).

## Naming convention

**Major Arcana (22):** `major_00.png` … `major_21.png`

| # | Card | File |
|---|------|------|
| 0 | Блазень | `major_00.png` |
| 1 | Маг | `major_01.png` |
| … | … | … |
| 21 | Мир | `major_21.png` |

**Minor Arcana (56):** `<suit>_<rank>.png`

- suits: `cups` (Кубки), `wands` (Жезли), `swords` (Мечі), `pentacles` (Пентаклі)
- ranks: `ace`, `02`, `03`, `04`, `05`, `06`, `07`, `08`, `09`, `10`, `page`, `knight`, `queen`, `king`

Examples: `cups_ace.png`, `wands_10.png`, `swords_queen.png`, `pentacles_king.png`.

> Full list of expected filenames: `python -c "import json;print('\n'.join(c['image'] for c in json.load(open('data/cards.json',encoding='utf-8'))))"`

## How to apply
1. Copy your PNGs into `cards/` (overwriting the placeholders of the same name).
2. No rebuild needed — `cards/` is a Docker volume.
3. Verify a render: `python tools/compose_image.py` → check the file in `.tmp/`.

## Regenerate placeholders (if needed)
```bash
python tools/make_placeholder_cards.py            # fills only missing files
python tools/make_placeholder_cards.py --force    # overwrite all (careful: wipes real scans)
```
