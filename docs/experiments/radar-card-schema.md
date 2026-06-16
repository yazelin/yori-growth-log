# radar-data.json card schema

`radar-v0.html` reads cards from `radar-data.json`. Add a card only when it can pass `append-radar-card.py` and `verify-radar.py`.

## Required card fields

```json
{
  "id": "stable-kebab-case-id",
  "title": "Human readable title",
  "kind": "verified | watch",
  "kindLabel": "verified repo | watchlist/search",
  "categories": ["data-game"],
  "tags": ["data→game"],
  "summary": "What this signal is and why it matters.",
  "use": "Yori 借用點：how Yori can turn it into a character/content/tool lesson.",
  "metrics": { "yoriFit": 8, "bizFit": 7, "teach": 9 },
  "href": "https://github.com/search?q=example&type=repositories",
  "linkLabel": "search →"
}
```

## Current category ids

- `data-game` — 資料 → 遊戲
- `story-3d` — 故事 → 3D
- `agent-world` — Agent → 可觀察世界
- `report-radar` — Report → Radar

## Safe append flow

```bash
python3 docs/experiments/append-radar-card.py /tmp/new-card.json --dry-run
python3 docs/experiments/append-radar-card.py /tmp/new-card.json
python3 docs/experiments/verify-radar.py
```

Rules:

1. Do not edit the HTML to add cards.
2. Do not reuse an `id`.
3. Keep `href` to public GitHub repo/search URLs only.
4. Keep the `use` field specific: what can Yori borrow, teach, or turn into an artifact?
5. After appending, verification output is part of the artifact, not an optional afterthought.
