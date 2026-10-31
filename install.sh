#!/usr/bin/env bash
# mp4-downloader installieren:
#   curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.sh | bash
set -euo pipefail

package="https://github.com/GamirHD/mp4-downloader/archive/refs/heads/main.zip"
install_root="${XDG_DATA_HOME:-$HOME/.local/share}/mp4-downloader"
venv_dir="$install_root/venv"
bin_dir="$HOME/.local/bin"

echo "Installiere mp4-downloader (vd)..."

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 fehlt. Installiere es zuerst (z. B. sudo apt install python3 python3-venv / brew install python)." >&2
  exit 1
fi

rm -rf "$venv_dir"
mkdir -p "$install_root" "$bin_dir"
if ! python3 -m venv "$venv_dir" >/dev/null 2>&1; then
  echo "Konnte keine Python-Umgebung anlegen. Unter Debian/Ubuntu: sudo apt install python3-venv" >&2
  exit 1
fi

"$venv_dir/bin/python" -m pip install --upgrade --quiet --disable-pip-version-check "$package"
# Browser für Logins und Seiten mit eigenem Video-Player (wird übersprungen, wenn es nicht klappt)
"$venv_dir/bin/python" -m playwright install chromium >/dev/null 2>&1 || true

ln -sf "$venv_dir/bin/vd" "$bin_dir/vd"

echo
echo "Fertig! Lade ein Video mit:"
echo '  vd "https://www.youtube.com/watch?v=..."'
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo
  echo "Hinweis: ffmpeg fehlt noch (z. B. sudo apt install ffmpeg / brew install ffmpeg)."
fi
if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
  echo
  echo "Hinweis: Füge ~/.local/bin zu deinem PATH hinzu:"
  echo '  echo '"'"'export PATH="$HOME/.local/bin:$PATH"'"'"' >> ~/.bashrc'
fi
