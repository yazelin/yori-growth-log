#!/usr/bin/env python3
"""Append one card to radar-data.json, then run the radar validator.

Local-only helper for Yori's radar experiment. It refuses duplicate ids,
checks the expected card shape, writes JSON with stable indentation, and then
runs verify-radar.py so a new signal card is never just "probably added".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "radar-data.json"
VERIFY_PATH = ROOT / "verify-radar.py"
REQUIRED_CARD_KEYS = {
    "id",
    "title",
    "kind",
    "kindLabel",
    "categories",
    "tags",
    "summary",
    "use",
    "metrics",
    "href",
    "linkLabel",
}
REQUIRED_METRICS = {"yoriFit", "bizFit", "teach"}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing {path}")
    except json.JSONDecodeError as exc:
        fail(f"{path.name} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail(f"{path.name} must contain a JSON object")
    return data


def validate_card(card: dict[str, Any], axis_ids: set[str]) -> None:
    missing = REQUIRED_CARD_KEYS - card.keys()
    if missing:
        fail(f"new card missing keys: {sorted(missing)}")

    if not isinstance(card["id"], str) or not card["id"].strip():
        fail("card id must be a non-empty string")
    if not isinstance(card["categories"], list) or not card["categories"]:
        fail("categories must be a non-empty list")
    unknown = set(card["categories"]) - axis_ids
    if unknown:
        fail(f"unknown categories: {sorted(unknown)}")
    if not isinstance(card["tags"], list):
        fail("tags must be a list")
    if not isinstance(card["metrics"], dict):
        fail("metrics must be an object")
    if not set(card["metrics"]).issuperset(REQUIRED_METRICS):
        fail(f"metrics must include {sorted(REQUIRED_METRICS)}")
    for metric in REQUIRED_METRICS:
        value = card["metrics"][metric]
        if not isinstance(value, (int, float)) or not 0 <= value <= 10:
            fail(f"metric {metric} must be a number from 0 to 10")
    if not isinstance(card["href"], str) or not card["href"].startswith("https://github.com/"):
        fail("href must be a public GitHub repo/search URL")


def run_verify() -> None:
    if not VERIFY_PATH.exists():
        fail(f"missing {VERIFY_PATH.name}")
    subprocess.run([sys.executable, str(VERIFY_PATH)], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Append a radar card and validate the radar dataset.")
    parser.add_argument("card_json", type=Path, help="Path to a JSON file containing exactly one card object")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the would-be card count without writing")
    args = parser.parse_args()

    data = load_json(DATA_PATH)
    card = load_json(args.card_json)

    axes = data.get("axes")
    cards = data.get("cards")
    if not isinstance(axes, list) or not isinstance(cards, list):
        fail("radar-data.json must contain axes and cards lists")
    axis_ids = {axis.get("id") for axis in axes if isinstance(axis, dict)}
    if not all(isinstance(axis_id, str) for axis_id in axis_ids):
        fail("all axes must have string ids")

    validate_card(card, axis_ids)  # type: ignore[arg-type]
    existing_ids = {item.get("id") for item in cards if isinstance(item, dict)}
    if card["id"] in existing_ids:
        fail(f"duplicate card id: {card['id']}")

    if args.dry_run:
        print(f"dry run ok: would append {card['id']} ({len(cards)} -> {len(cards) + 1} cards)")
        return

    cards.append(card)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"appended {card['id']} ({len(cards)} cards)")
    run_verify()


if __name__ == "__main__":
    main()
