#!/usr/bin/env python3
"""Validate that radar-v0.html is driven by radar-data.json."""
from __future__ import annotations

import html.parser
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "radar-v0.html"
DATA_PATH = ROOT / "radar-data.json"


class CardParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.card_articles = 0
        self.buttons: list[str] = []
        self._in_button = False
        self._button_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "article" and "card" in (attrs_dict.get("class") or "").split():
            self.card_articles += 1
        if tag == "button" and attrs_dict.get("data-filter"):
            self._in_button = True
            self._button_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._in_button:
            self.buttons.append("".join(self._button_chunks).strip())
            self._in_button = False

    def handle_data(self, data: str) -> None:
        if self._in_button:
            self._button_chunks.append(data)


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not HTML_PATH.exists():
        fail(f"missing {HTML_PATH}")
    if not DATA_PATH.exists():
        fail(f"missing {DATA_PATH.name}; radar cards must live in JSON now")

    html_text = HTML_PATH.read_text(encoding="utf-8")
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    parser = CardParser()
    parser.feed(html_text)

    if parser.card_articles:
        fail(f"HTML still contains {parser.card_articles} hard-coded card articles")
    if "radar-data.json" not in html_text:
        fail("HTML does not load radar-data.json")
    if 'id="cards"' not in html_text:
        fail("HTML missing #cards render target")

    axes = data.get("axes")
    cards = data.get("cards")
    filters = data.get("filters")
    if not isinstance(axes, list) or len(axes) != 4:
        fail("radar-data.json must contain exactly 4 axes")
    if not isinstance(cards, list) or len(cards) < 8:
        fail("radar-data.json must contain at least 8 cards")
    if not isinstance(filters, list) or len(filters) < 5:
        fail("radar-data.json must contain filters including all")

    required_card_keys = {"id", "title", "kind", "categories", "tags", "summary", "use", "metrics", "href", "linkLabel"}
    required_metrics = {"yoriFit", "bizFit", "teach"}
    ids = set()
    for i, card in enumerate(cards, 1):
        missing = required_card_keys - card.keys()
        if missing:
            fail(f"card #{i} missing keys: {sorted(missing)}")
        if card["id"] in ids:
            fail(f"duplicate card id: {card['id']}")
        ids.add(card["id"])
        if not set(card["metrics"].keys()) >= required_metrics:
            fail(f"card {card['id']} missing metric keys")
        if not card["href"].startswith("https://github.com/"):
            fail(f"card {card['id']} href is not a GitHub public/search link")

    print(f"radar data ok: {len(axes)} axes, {len(filters)} filters, {len(cards)} cards")


if __name__ == "__main__":
    main()
