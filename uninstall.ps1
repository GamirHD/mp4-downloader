# mp4-downloader entfernen:
#   irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.ps1 | iex
$ErrorActionPreference = "Stop"

Write-Host "Entferne mp4-downloader..."
if (Get-Command python -ErrorAction SilentlyContinue) {
    python -m pip uninstall -y --quiet mp4-downloader
}
foreach ($dir in @((Join-Path $env:APPDATA "mp4-downloader"), (Join-Path $env:LOCALAPPDATA "mp4-downloader"))) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
Write-Host "Fertig. Einstellungen und gespeicherte Logins wurden ebenfalls gelöscht."
