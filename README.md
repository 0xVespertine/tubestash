# TubeStash

A small, polished Windows desktop app for downloading YouTube videos —
a clean GUI on top of [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), with a
built-in history and a self-updating engine so it doesn't rot.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Video preview** — paste a link and see the thumbnail, title, channel
  and duration before you download.
- **Quality picker** — Best (MP4), 1080p, 720p, or Audio-only (MP3).
- **Remembers your save folder** between runs.
- **Live progress** — percent, speed, ETA.
- **History** in a single `history.json` file (no database). Right-click
  to open the file, show it in Explorer, copy the link, or remove it.
- **Self-updating engine** — on launch it checks PyPI and silently
  upgrades `yt-dlp` if YouTube broke the current version. This is why the
  app keeps working instead of dying after a few weeks.
- Playlist support, RTL-aware titles, no console window.

## Requirements

- **Windows** with **Python 3.10+**
- **ffmpeg** on `PATH` (needed for >720p merging and MP3 extraction):
  ```powershell
  winget install Gyan.FFmpeg
  ```

## Install

```powershell
git clone https://github.com/<your-user>/tubestash.git
cd tubestash
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` creates a local virtual environment, installs dependencies,
and adds a Desktop shortcut. Then launch from the **YouTube Downloader**
shortcut (or run `YouTube Downloader.vbs`).

## Project layout

| Path | Purpose |
|------|---------|
| `main.py` | Entry point |
| `ytdl_app/config.py` | Settings + ffmpeg detection |
| `ytdl_app/history.py` | JSON history |
| `ytdl_app/worker.py` | Download / preview / engine-update threads |
| `ytdl_app/ui.py` | The window (PySide6) |
| `YouTube Downloader.vbs` | Silent launcher (no console) |
| `setup.ps1` | One-time installer for a fresh clone |

`settings.json` and `history.json` are created on first use and are
git-ignored (they contain machine-specific paths and personal history).

## Disclaimer

For personal and educational use. Downloading content may be subject to
YouTube's Terms of Service and applicable copyright law — you are
responsible for how you use this tool.

## License

[MIT](LICENSE)
