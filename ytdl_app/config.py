"""Settings + paths. Plain JSON files next to the app, no database."""
from __future__ import annotations

import glob
import json
import os
import shutil
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.json"

DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads")

DEFAULTS = {
    "download_dir": DEFAULT_DOWNLOAD_DIR,
    "quality": "Best (MP4)",
    "playlist": False,
    "auto_update_engine": True,
}


def load_settings() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data.update(json.load(fh))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    # Heal an invalid/missing download dir so the app always opens usable.
    if not os.path.isdir(data.get("download_dir", "")):
        data["download_dir"] = DEFAULT_DOWNLOAD_DIR
    return data


def save_settings(data: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass


def find_ffmpeg() -> str | None:
    """Return the directory containing ffmpeg.exe, or None.

    yt-dlp wants the *folder*, not the binary path. We prefer PATH, then
    the known local build, so high-res merges + mp3 extraction work.
    """
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).parent)
    # Common locations where ffmpeg lands when not added to PATH.
    for pat in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\tools\ffmpeg*\bin\ffmpeg.exe",
        str(Path.home() / r"scoop\apps\ffmpeg\current\bin\ffmpeg.exe"),
    ):
        for hit in glob.glob(pat):
            if Path(hit).exists():
                return str(Path(hit).parent)
    return None
