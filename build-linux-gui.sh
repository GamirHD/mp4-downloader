#!/usr/bin/env bash
set -euo pipefail

echo "Building Linux GUI app..."

python3 -m venv .venv-build
. .venv-build/bin/activate

python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller -r requirements.txt

rm -rf dist build

python -m PyInstaller \
  --onefile \
  --name mp4-downloader \
  run.py

echo
echo "Done:"
echo " dist/mp4-downloader"
