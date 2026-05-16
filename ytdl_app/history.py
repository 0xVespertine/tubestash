"""Append-only download history in a single JSON file (newest first)."""
from __future__ import annotations

import json
from datetime import datetime

from .config import HISTORY_FILE

MAX_ENTRIES = 500


def load_history() -> list[dict]:
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _write(entries: list[dict]) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(entries[:MAX_ENTRIES], fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def add_entry(title: str, url: str, filepath: str, quality: str) -> dict:
    entry = {
        "title": title,
        "url": url,
        "filepath": filepath,
        "quality": quality,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    entries = load_history()
    entries.insert(0, entry)
    _write(entries)
    return entry


def remove_entry(index: int) -> None:
    entries = load_history()
    if 0 <= index < len(entries):
        del entries[index]
        _write(entries)


def clear_history() -> None:
    _write([])
