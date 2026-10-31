# Install mp4-downloader (window app + command vd):
#   irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$setupUrl = "https://github.com/GamirHD/mp4-downloader/releases/latest/download/mp4-downloader-setup.exe"
$setup = Join-Path $env:TEMP "mp4-downloader-setup.exe"

Write-Host "Downloading Video Downloader..."
Invoke-WebRequest -Uri $setupUrl -OutFile $setup -UseBasicParsing

Write-Host "Installing (this can take a minute)..."
$process = Start-Process -FilePath $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
Remove-Item $setup -Force -ErrorAction SilentlyContinue
if ($process.ExitCode -ne 0) { throw "Installation failed (code $($process.ExitCode))." }

# Make vd usable in this window right away
$appDir = Join-Path $env:LOCALAPPDATA "Programs\mp4-downloader"
if (@($env:Path -split ";") -notcontains $appDir) { $env:Path = "$env:Path;$appDir" }

Write-Host ""
Write-Host "Done! Start 'Video Downloader' from the Start menu, or download in a terminal with:"
Write-Host '  vd "https://www.youtube.com/watch?v=..."'
Write-Host "Deutsch: vd settings --language de"
