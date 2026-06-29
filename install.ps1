$ErrorActionPreference = "Stop"

$repoUrl = "https://github.com/GamirHD/mp4-downloader"
$archiveUrl = "$repoUrl/archive/refs/heads/main.zip"
$installRoot = Join-Path $env:LOCALAPPDATA "mp4-downloader"
$sourceDir = Join-Path $installRoot "source"
$zipPath = Join-Path $env:TEMP "mp4-downloader-main.zip"

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$PackageId,
        [Parameter(Mandatory = $true)][string]$CommandName,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )

    if (Test-Command $CommandName) {
        Write-Host "$DisplayName ist bereits installiert."
        return
    }

    if (-not (Test-Command "winget")) {
        throw "$DisplayName fehlt und winget wurde nicht gefunden. Bitte $DisplayName manuell installieren."
    }

    Write-Host "Installiere $DisplayName mit winget..."
    winget install --id $PackageId --exact --source winget --accept-package-agreements --accept-source-agreements
}

Write-Host "Installiere mp4-downloader..."

Ensure-WingetPackage -PackageId "Python.Python.3.12" -CommandName "python" -DisplayName "Python"
Ensure-WingetPackage -PackageId "Gyan.FFmpeg" -CommandName "ffmpeg" -DisplayName "ffmpeg"

if (Test-Path $installRoot) {
    Remove-Item $installRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $installRoot | Out-Null

Write-Host "Lade Projekt von GitHub..."
Invoke-WebRequest -Uri $archiveUrl -OutFile $zipPath
Expand-Archive -Path $zipPath -DestinationPath $installRoot -Force
Remove-Item $zipPath -Force

$expandedDir = Join-Path $installRoot "mp4-downloader-main"
Move-Item $expandedDir $sourceDir

Write-Host "Installiere vd-Befehl..."
python -m pip install --upgrade pip
python -m pip install --upgrade $sourceDir

Write-Host ""
Write-Host "Fertig. Schliesse dieses Terminal und oeffne ein neues."
Write-Host "Danach kannst du verwenden:"
Write-Host '  vd "https://www.youtube.com/watch?v=..."'
Write-Host ""
Write-Host "Settings:"
Write-Host "  vd settings"
Write-Host '  vd settings --folder "C:\Users\Kadir\Downloads\Videos"'
