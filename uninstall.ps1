$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "mp4-downloader"

Write-Host "Deinstalliere mp4-downloader..."

if (Get-Command python -ErrorAction SilentlyContinue) {
    python -m pip uninstall -y mp4-downloader
} else {
    Write-Host "Python wurde nicht gefunden. Ueberspringe pip uninstall."
}

if (Test-Path $installRoot) {
    Remove-Item $installRoot -Recurse -Force
}

Write-Host "Fertig."
