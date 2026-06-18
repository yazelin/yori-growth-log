#!/usr/bin/env python3
"""Smoke-check radar render/filter visibility from radar-data.json.

This is a small reusable companion to verify-radar.py. The validator checks
shape and wiring; this smoke check asks the beginner-facing question: if the
page filters cards the way radar-v0.html does, which cards are visible where?
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "radar-data.json"
DEFAULT_TARGET = "growth-log-validator-chain-pattern"


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_data() -> dict[str, Any]:
    try:
        raw_data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing {DATA_PATH.name}")
    except json.JSONDecodeError as exc:
        fail(f"{DATA_PATH.name} is not valid JSON: {exc}")
    if not isinstance(raw_data, dict):
        fail(f"{DATA_PATH.name} must contain a JSON object")
    return raw_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-check radar card filter visibility.")
    parser.add_argument("--target-id", default=DEFAULT_TARGET, help="Card id that should be visible in its category filters")
    args = parser.parse_args()

    data = load_data()
    filters = data.get("filters")
    cards = data.get("cards")
    if not isinstance(filters, list) or not isinstance(cards, list):
        fail("radar-data.json must contain filters and cards lists")

    filter_ids = [item.get("id") for item in filters if isinstance(item, dict)]
    if "all" not in filter_ids:
        fail("filters must include all")
    category_filter_ids = {item for item in filter_ids if isinstance(item, str) and item != "all"}

    counts: Counter[str] = Counter({"all": len(cards)})
    target_card: dict[str, Any] | None = None
    for card in cards:
        if not isinstance(card, dict):
            fail("every card must be an object")
        if card.get("id") == args.target_id:
            target_card = card
        categories = card.get("categories")
        if not isinstance(categories, list) or not categories:
            fail(f"card {card.get('id', '<unknown>')} must have categories")
        unknown = set(categories) - category_filter_ids
        if unknown:
            fail(f"card {card.get('id', '<unknown>')} uses categories without filters: {sorted(unknown)}")
        for category in categories:
            counts[category] += 1

    if target_card is None:
        fail(f"target card not found: {args.target_id}")

    target_categories = target_card.get("categories")
    if not isinstance(target_categories, list) or not target_categories:
        fail(f"target card {args.target_id} has no categories")
    visible_in = [category for category in target_categories if counts[category] > 0]
    if set(visible_in) != set(target_categories):
        fail(f"target card {args.target_id} is not visible in all categories: {target_categories}")

    ordered_counts = {filter_id: counts[filter_id] for filter_id in filter_ids if isinstance(filter_id, str)}
    print(
        "render smoke ok: "
        f"{len(cards)} cards; {args.target_id} visible in {', '.join(visible_in)}; "
        f"filter counts {ordered_counts}"
    )


if __name__ == "__main__":
    main()
