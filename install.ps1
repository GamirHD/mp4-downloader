# mp4-downloader installieren (Programm mit Oberfläche + Befehl vd):
#   irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$setupUrl = "https://github.com/GamirHD/mp4-downloader/releases/latest/download/mp4-downloader-setup.exe"
$setup = Join-Path $env:TEMP "mp4-downloader-setup.exe"

Write-Host "Lade Video-Downloader..."
Invoke-WebRequest -Uri $setupUrl -OutFile $setup -UseBasicParsing

Write-Host "Installiere (das kann eine Minute dauern)..."
$process = Start-Process -FilePath $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
Remove-Item $setup -Force -ErrorAction SilentlyContinue
if ($process.ExitCode -ne 0) { throw "Installation fehlgeschlagen (Code $($process.ExitCode))." }

# vd sofort in diesem Fenster nutzbar machen
$appDir = Join-Path $env:LOCALAPPDATA "Programs\mp4-downloader"
if (@($env:Path -split ";") -notcontains $appDir) { $env:Path = "$env:Path;$appDir" }

Write-Host ""
Write-Host "Fertig! Im Startmenü findest du jetzt den 'Video-Downloader'."
Write-Host "Im Terminal lädst du Videos mit:"
Write-Host '  vd "https://www.youtube.com/watch?v=..."'
