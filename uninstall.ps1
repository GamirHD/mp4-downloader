# mp4-downloader entfernen (geht auch über Einstellungen > Apps > Video-Downloader):
#   irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.ps1 | iex
$ErrorActionPreference = "Stop"
$uninstaller = Join-Path $env:LOCALAPPDATA "Programs\mp4-downloader\unins000.exe"

if (Test-Path $uninstaller) {
    Write-Host "Entferne Video-Downloader..."
    Start-Process -FilePath $uninstaller -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
}
# Ältere Installation über pip
if ((Get-Command python -ErrorAction SilentlyContinue) -and (python -m pip show mp4-downloader 2>$null)) {
    python -m pip uninstall -y --quiet mp4-downloader
}
$dataDir = Join-Path $env:APPDATA "mp4-downloader"
if (Test-Path $dataDir) { Remove-Item $dataDir -Recurse -Force }
Write-Host "Fertig. Einstellungen und gespeicherte Logins wurden ebenfalls gelöscht."
