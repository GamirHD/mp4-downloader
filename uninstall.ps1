# Remove mp4-downloader (also possible via Settings > Apps > Video Downloader):
#   irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.ps1 | iex
$ErrorActionPreference = "Stop"
$uninstaller = Join-Path $env:LOCALAPPDATA "Programs\mp4-downloader\unins000.exe"

if (Test-Path $uninstaller) {
    Write-Host "Removing Video Downloader..."
    Start-Process -FilePath $uninstaller -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
}
# Older installation via pip
if ((Get-Command python -ErrorAction SilentlyContinue) -and (python -m pip show mp4-downloader 2>$null)) {
    python -m pip uninstall -y --quiet mp4-downloader
}
$dataDir = Join-Path $env:APPDATA "mp4-downloader"
if (Test-Path $dataDir) { Remove-Item $dataDir -Recurse -Force }
Write-Host "Done. Settings and saved logins were removed too."
