#!/usr/bin/env bash
set -euo pipefail

install_root="${XDG_DATA_HOME:-$HOME/.local/share}/mp4-downloader"
bin_path="$HOME/.local/bin/vd"

echo "Deinstalliere mp4-downloader..."

if [[ -x "$install_root/venv/bin/python" ]]; then
  "$install_root/venv/bin/python" -m pip uninstall -y mp4-downloader >/dev/null 2>&1 || true
fi

rm -rf "$install_root"
rm -f "$bin_path"

echo "Fertig."
