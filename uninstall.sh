#!/usr/bin/env bash
# mp4-downloader entfernen
set -euo pipefail
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/mp4-downloader" "${XDG_CONFIG_HOME:-$HOME/.config}/mp4-downloader"
rm -f "$HOME/.local/bin/vd"
echo "mp4-downloader wurde entfernt (inklusive Einstellungen und gespeicherter Logins)."
