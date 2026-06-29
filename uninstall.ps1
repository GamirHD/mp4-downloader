$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "mp4-downloader"

Write-Host "Deinstalliere mp4-downloader..."

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -m pip uninstall -y mp4-downloader
} else {
    Write-Host "Python Launcher 'py' wurde nicht gefunden. Ueberspringe pip uninstall."
}

if (Test-Path $installRoot) {
    Remove-Item $installRoot -Recurse -Force
}

Write-Host "Fertig."
