"""Background workers: the download itself, and the yt-dlp self-updater.

yt-dlp is used as a library (not a subprocess) so progress + errors come
through structured hooks instead of scraped stdout.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import urllib.request
import json

from PySide6.QtCore import QThread, Signal

import yt_dlp

try:
    from yt_dlp.utils import DownloadCancelled
except ImportError:  # very old yt-dlp fallback
    class DownloadCancelled(Exception):
        pass


def build_opts(quality: str, out_dir: str, playlist: bool, ffmpeg_dir: str | None):
    """Map a friendly quality label to yt-dlp options."""
    opts = {
        "outtmpl": {"default": f"{out_dir}/%(title)s.%(ext)s"},
        "noplaylist": not playlist,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
        "restrictfilenames": False,
        "windowsfilenames": True,
        "concurrent_fragment_downloads": 4,
    }
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    if quality == "Audio only (MP3)":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    elif quality == "1080p":
        opts["format"] = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        opts["merge_output_format"] = "mp4"
    elif quality == "720p":
        opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        opts["merge_output_format"] = "mp4"
    else:  # Best (MP4)
        opts["format"] = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        )
        opts["merge_output_format"] = "mp4"
    return opts


def _friendly_error(msg: str) -> str:
    low = msg.lower()
    if "private video" in low:
        return "This video is private."
    if "sign in to confirm your age" in low or "age" in low and "restrict" in low:
        return "Age-restricted video — YouTube blocks it without sign-in."
    if "members-only" in low or "join this channel" in low:
        return "Members-only video — not downloadable."
    if "video unavailable" in low:
        return "Video unavailable (removed, region-locked, or deleted)."
    if "is not a valid url" in low or "unsupported url" in low:
        return "That doesn't look like a valid video URL."
    if "ffmpeg" in low:
        return "ffmpeg problem — high-res merge/MP3 needs ffmpeg on PATH."
    # Trim yt-dlp's "ERROR: " prefix for readability.
    return msg.split("ERROR:")[-1].strip() or "Download failed."


class DownloadWorker(QThread):
    progress = Signal(float, str, str, str)   # percent, speed, eta, filename
    stage = Signal(str)                       # human status line
    done = Signal(list)                       # list of (title, url, path, q)
    failed = Signal(str)

    def __init__(self, url: str, quality: str, out_dir: str,
                 playlist: bool, ffmpeg_dir: str | None):
        super().__init__()
        self.url = url.strip()
        self.quality = quality
        self.out_dir = out_dir
        self.playlist = playlist
        self.ffmpeg_dir = ffmpeg_dir
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    # --- yt-dlp hooks (run in this thread) ---
    def _progress_hook(self, d: dict) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            pct = (got / total * 100) if total else 0.0
            speed = d.get("_speed_str", "").strip() or "—"
            eta = d.get("_eta_str", "").strip() or "—"
            name = d.get("info_dict", {}).get("title", "")
            self.progress.emit(pct, speed, eta, name)
        elif d.get("status") == "finished":
            self.stage.emit("Merging / converting…")

    def run(self) -> None:
        opts = build_opts(self.quality, self.out_dir, self.playlist,
                           self.ffmpeg_dir)
        opts["progress_hooks"] = [self._progress_hook]
        try:
            self.stage.emit("Fetching video info…")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
            if self._cancel.is_set():
                self.failed.emit("Cancelled.")
                return

            entries = info.get("entries") or [info]
            results = []
            for item in entries:
                if not item:
                    continue
                title = item.get("title", "Unknown")
                reqs = item.get("requested_downloads") or []
                path = reqs[0].get("filepath") if reqs else ""
                results.append((title, self.url, path, self.quality))
            self.done.emit(results)
        except DownloadCancelled:
            self.failed.emit("Cancelled.")
        except yt_dlp.utils.DownloadError as exc:
            self.failed.emit(_friendly_error(str(exc)))
        except Exception as exc:  # noqa: BLE001 - surface anything to the UI
            self.failed.emit(_friendly_error(str(exc)))


class InfoWorker(QThread):
    """Fetch lightweight metadata + thumbnail for the preview card,
    without downloading the video."""
    loaded = Signal(dict)   # {title, uploader, duration, thumb (bytes|None)}
    failed = Signal()

    def __init__(self, url: str):
        super().__init__()
        self.url = url.strip()

    def run(self) -> None:
        try:
            opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                    "noplaylist": True, "extract_flat": False}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            if info.get("entries"):  # playlist URL -> first item
                info = info["entries"][0]
            thumb = None
            turl = info.get("thumbnail")
            if turl:
                try:
                    req = urllib.request.Request(
                        turl, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        thumb = r.read()
                except Exception:  # noqa: BLE001 - thumbnail is optional
                    thumb = None
            dur = info.get("duration") or 0
            self.loaded.emit({
                "title": info.get("title", "Unknown"),
                "uploader": info.get("uploader") or info.get("channel") or "",
                "duration": f"{int(dur)//60}:{int(dur)%60:02d}" if dur else "",
                "thumb": thumb,
            })
        except Exception:  # noqa: BLE001 - preview is best-effort
            self.failed.emit()


class EngineUpdater(QThread):
    """Keep yt-dlp current. YouTube breaks it constantly; a frozen
    engine silently dies within weeks. Checks PyPI, upgrades if newer."""
    result = Signal(str)  # status message for the UI

    def run(self) -> None:
        try:
            current = yt_dlp.version.__version__
            with urllib.request.urlopen(
                "https://pypi.org/pypi/yt-dlp/json", timeout=8
            ) as resp:
                latest = json.load(resp)["info"]["version"]
            if latest == current:
                self.result.emit(f"Engine up to date (yt-dlp {current})")
                return
            self.result.emit(f"Updating engine → {latest}…")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U",
                 "--quiet", "yt-dlp"],
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.result.emit(
                f"Engine updated to {latest} — restart app to apply"
            )
        except Exception:  # noqa: BLE001 - update is best-effort, never fatal
            self.result.emit(
                f"Engine: offline check skipped (yt-dlp "
                f"{yt_dlp.version.__version__})"
            )
