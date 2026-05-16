# One-time setup for a fresh clone.
#   Right-click > Run with PowerShell   (or:  powershell -ExecutionPolicy Bypass -File setup.ps1)
$ErrorActionPreference = "Stop"
$proj = $PSScriptRoot

Write-Host "Creating virtual environment..." -ForegroundColor Cyan
python -m venv "$proj\.venv"

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& "$proj\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$proj\.venv\Scripts\python.exe" -m pip install --quiet -r "$proj\requirements.txt"

Write-Host "Creating Desktop shortcut..." -ForegroundColor Cyan
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'YouTube Downloader.lnk'))
$lnk.TargetPath = "$proj\YouTube Downloader.vbs"
$lnk.WorkingDirectory = $proj
$lnk.IconLocation = "$proj\.venv\Scripts\pythonw.exe,0"
$lnk.Description = "Download YouTube videos"
$lnk.Save()

Write-Host ""
Write-Host "Done. Launch from the Desktop shortcut, or run 'YouTube Downloader.vbs'." -ForegroundColor Green
Write-Host "Make sure ffmpeg is installed and on PATH (winget install Gyan.FFmpeg)." -ForegroundColor Yellow
