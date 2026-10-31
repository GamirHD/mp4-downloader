#!/usr/bin/env bash
# Install mp4-downloader (window app + command vd) on Linux or macOS:
#   curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.sh | bash
set -euo pipefail

package="${VD_PACKAGE:-https://github.com/GamirHD/mp4-downloader/archive/refs/heads/main.zip}"
install_root="${XDG_DATA_HOME:-$HOME/.local/share}/mp4-downloader"
venv_dir="$install_root/venv"
bin_dir="$HOME/.local/bin"
app_name="Video Downloader"

echo "Installing $app_name (vd)..."

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is missing. Install it first (e.g. sudo apt install python3 python3-venv / brew install python)." >&2
  exit 1
fi

rm -rf "$venv_dir"
mkdir -p "$install_root" "$bin_dir"
if ! python3 -m venv "$venv_dir" >/dev/null 2>&1; then
  echo "Could not create a Python environment. On Debian/Ubuntu: sudo apt install python3-venv" >&2
  exit 1
fi

"$venv_dir/bin/python" -m pip install --upgrade --quiet --disable-pip-version-check "$package"
# Browser for logins and pages with their own video player (skipped if it fails)
"$venv_dir/bin/python" -m playwright install chromium >/dev/null 2>&1 || true

ln -sf "$venv_dir/bin/vd" "$bin_dir/vd"
ln -sf "$venv_dir/bin/vd-gui" "$bin_dir/vd-gui"

# Entry in the app menu / Applications folder
if [[ "$(uname -s)" == "Darwin" ]]; then
  app="$HOME/Applications/$app_name.app"
  rm -rf "$app"
  mkdir -p "$app/Contents/MacOS"
  cat > "$app/Contents/MacOS/video-downloader" <<LAUNCHER
#!/bin/bash
exec "$venv_dir/bin/vd-gui"
LAUNCHER
  chmod +x "$app/Contents/MacOS/video-downloader"
  cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$app_name</string>
  <key>CFBundleDisplayName</key><string>$app_name</string>
  <key>CFBundleIdentifier</key><string>io.github.gamirhd.mp4-downloader</string>
  <key>CFBundleExecutable</key><string>video-downloader</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
else
  apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$apps_dir"
  "$venv_dir/bin/python" -c "import app_icon; app_icon.write_png('$install_root/icon.png')"
  cat > "$apps_dir/mp4-downloader.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$app_name
Comment=Download videos from a link as MP4 or MP3
Exec="$venv_dir/bin/vd-gui"
Icon=$install_root/icon.png
Terminal=false
Categories=AudioVideo;Network;
DESKTOP
fi

echo
echo "Done! Start \"$app_name\" from your app menu, or download in a terminal with:"
echo '  vd "https://www.youtube.com/watch?v=..."'
if ! "$venv_dir/bin/python" -c "import tkinter" >/dev/null 2>&1; then
  echo
  echo "Note: the window app needs Tk (e.g. sudo apt install python3-tk / brew install python-tk)."
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo
  echo "Note: ffmpeg is missing (e.g. sudo apt install ffmpeg / brew install ffmpeg)."
fi
if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
  echo
  echo "Note: add ~/.local/bin to your PATH:"
  echo '  echo '"'"'export PATH="$HOME/.local/bin:$PATH"'"'"' >> ~/.bashrc'
fi
