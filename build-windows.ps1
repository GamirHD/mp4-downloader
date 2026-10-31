# Baut den Windows-Installer dist\mp4-downloader-setup.exe
# (Programm mit Oberfläche + Befehl vd in einem Paket). Benötigt Python und Inno Setup 6.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade --quiet pip
python -m pip install --upgrade --quiet pyinstaller -r requirements.txt playwright

Remove-Item -Recurse -Force dist, build, dist-cli -ErrorAction SilentlyContinue

# Programm mit Oberfläche (ohne Konsolenfenster)
python -m PyInstaller --noconfirm --onedir --windowed --name mp4-downloader --collect-all playwright run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (GUI) fehlgeschlagen" }

# Befehl vd (Konsole), danach in denselben Ordner legen
python -m PyInstaller --noconfirm --onedir --console --name vd --collect-all playwright --distpath dist-cli vd_main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (vd) fehlgeschlagen" }
Copy-Item dist-cli\vd\vd.exe dist\mp4-downloader\ -Force
Copy-Item dist-cli\vd\_internal\* dist\mp4-downloader\_internal\ -Recurse -Force

& dist\mp4-downloader\vd.exe --version
if ($LASTEXITCODE -ne 0) { throw "vd.exe startet nicht" }

$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
$iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
& $iscc /Qp "/DMyAppVersion=$version" installer-windows.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup fehlgeschlagen" }

Write-Host "Fertig: dist\mp4-downloader-setup.exe"
