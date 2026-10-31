#!/usr/bin/env bash
# Remove mp4-downloader (Linux/macOS), including settings and saved logins.
set -euo pipefail
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/mp4-downloader" "${XDG_CONFIG_HOME:-$HOME/.config}/mp4-downloader"
rm -f "$HOME/.local/bin/vd" "$HOME/.local/bin/vd-gui"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/mp4-downloader.desktop"
rm -rf "$HOME/Applications/Video Downloader.app"
echo "mp4-downloader was removed (including settings and saved logins)."
