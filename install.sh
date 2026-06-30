#!/usr/bin/env bash
set -euo pipefail

repo_url="https://github.com/GamirHD/mp4-downloader"
archive_url="$repo_url/archive/refs/heads/main.tar.gz"
install_root="${XDG_DATA_HOME:-$HOME/.local/share}/mp4-downloader"
source_dir="$install_root/source"
venv_dir="$install_root/venv"
bin_dir="$HOME/.local/bin"
tmp_dir="$(mktemp -d)"

cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

need_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Fehlt: $1" >&2
    return 1
  fi
}

echo "Installiere mp4-downloader fuer Linux..."

need_command python3
need_command curl
need_command tar

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Hinweis: ffmpeg wurde nicht gefunden. Installiere es mit deinem Paketmanager, z. B.:" >&2
  echo "  sudo apt install ffmpeg" >&2
  echo "  sudo dnf install ffmpeg" >&2
  echo "  sudo pacman -S ffmpeg" >&2
fi

rm -rf "$install_root"
mkdir -p "$install_root" "$bin_dir"

echo "Lade Projekt von GitHub..."
curl -fsSL "$archive_url" -o "$tmp_dir/mp4-downloader.tar.gz"
tar -xzf "$tmp_dir/mp4-downloader.tar.gz" -C "$tmp_dir"
mv "$tmp_dir/mp4-downloader-main" "$source_dir"

echo "Erstelle lokale Python-Umgebung..."
if ! python3 -m venv "$venv_dir"; then
  echo "Konnte keine Python-venv erstellen." >&2
  echo "Installiere das venv-Paket, z. B. unter Debian/Ubuntu:" >&2
  echo "  sudo apt install python3-venv" >&2
  exit 1
fi

"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install --upgrade "$source_dir"

cat > "$bin_dir/vd" <<EOF
#!/usr/bin/env bash
exec "$venv_dir/bin/vd" "\$@"
EOF
chmod +x "$bin_dir/vd"

echo
echo "Fertig."
echo "vd wurde installiert nach: $bin_dir/vd"
if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
  echo
  echo "Hinweis: $bin_dir ist noch nicht in PATH."
  echo "Fuege diese Zeile zu ~/.bashrc, ~/.zshrc oder deiner Shell-Konfiguration hinzu:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo
echo "Danach kannst du verwenden:"
echo '  vd "https://www.youtube.com/watch?v=..."'
echo "  vd settings"
