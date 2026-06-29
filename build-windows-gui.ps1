$ErrorActionPreference = "Stop"

Write-Host "Baue Windows-GUI-App..."

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python wurde nicht gefunden."
}

python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller -r requirements.txt

if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}
if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

python -m PyInstaller `
    --onefile `
    --windowed `
    --name "mp4-downloader" `
    run.py

Write-Host ""
Write-Host "Fertig:"
Write-Host " dist\mp4-downloader.exe"
