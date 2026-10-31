# mp4-downloader installieren:
#   irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$package = "https://github.com/GamirHD/mp4-downloader/archive/refs/heads/main.zip"

function Test-Command([string]$Name) {
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Install-WithWinget([string]$Id, [string]$Command, [string]$Name) {
    if (Test-Command $Command) { return }
    if (-not (Test-Command "winget")) {
        throw "$Name fehlt und winget ist nicht verfügbar. Bitte $Name installieren und das Skript erneut starten."
    }
    Write-Host "Installiere $Name..."
    winget install --id $Id --exact --source winget --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Update-SessionPath
}

function Add-ToUserPath([string]$Dir) {
    if (-not $Dir -or -not (Test-Path $Dir)) { return }
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($user -split ";" | Where-Object { $_ })
    if ($parts -notcontains $Dir) {
        [Environment]::SetEnvironmentVariable("Path", (($parts + $Dir) -join ";"), "User")
    }
    if (@($env:Path -split ";") -notcontains $Dir) { $env:Path = "$env:Path;$Dir" }
}

Write-Host "Installiere mp4-downloader (vd)..."
Install-WithWinget "Python.Python.3.12" "python" "Python"
Install-WithWinget "Gyan.FFmpeg" "ffmpeg" "ffmpeg"

python -m pip install --upgrade --quiet --disable-pip-version-check $package
if ($LASTEXITCODE -ne 0) { throw "Installation fehlgeschlagen." }

# Ordner mit vd.exe in den PATH aufnehmen (normale und Benutzer-Installation von pip)
Add-ToUserPath (python -c "import sysconfig; print(sysconfig.get_path('scripts'))")
Add-ToUserPath (python -c "import os, sysconfig; print(sysconfig.get_path('scripts', os.name + '_user'))")

Write-Host ""
Write-Host "Fertig! Öffne ein neues Terminal und lade ein Video mit:"
Write-Host '  vd "https://www.youtube.com/watch?v=..."'
Write-Host ""
Write-Host "Hilfe: vd --help    Aktualisieren: vd update"
