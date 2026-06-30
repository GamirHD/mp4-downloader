# mp4-downloader

Simple desktop and CLI app for downloading supported video links as MP4 or MP3.

## Features

- Download one or more video links as MP4 or MP3
- Quality choices: best, 1080p, 720p, 480p, MP3
- Windows/Linux/macOS GUI builds in GitHub releases
- Windows setup installer for the GUI
- CLI command: `vd "https://..."`
- Saved default download folder shared by GUI and CLI
- Clearer error messages for common YouTube blocks

## Before Installing

The app needs `ffmpeg` for merging MP4 files and converting MP3 audio.

### Windows

The Windows GUI setup can install `ffmpeg` automatically via `winget` if it is missing.
For CLI usage or manual setup, run:

```powershell
winget install --id Python.Python.3.12 --exact --source winget
winget install --id Gyan.FFmpeg --exact --source winget
```

Close the terminal afterwards and open a new CMD or PowerShell window.

### Linux

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-venv ffmpeg curl
```

Fedora:

```bash
sudo dnf install python3 ffmpeg curl
```

Arch Linux:

```bash
sudo pacman -S python ffmpeg curl
```

### macOS

Install Homebrew if needed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install the tools:

```bash
brew install python ffmpeg curl
```

Check `ffmpeg` on any system with:

```bash
ffmpeg -version
```

## GUI Installation

Download the latest release:

`https://github.com/GamirHD/mp4-downloader/releases/latest`

Windows recommended:

1. Download `mp4-downloader-setup.exe`.
2. Run the setup.
3. If `ffmpeg` is missing, the setup installs it automatically with `winget`.
4. Start `mp4-downloader` from the Start menu or desktop shortcut.

Windows portable:

- Download `mp4-downloader.exe` and double-click it.

Linux:

```bash
chmod +x mp4-downloader-linux
./mp4-downloader-linux
```

macOS:

```bash
chmod +x mp4-downloader-macos
./mp4-downloader-macos
```

If macOS blocks the unsigned app, allow it in System Settings or remove quarantine:

```bash
xattr -d com.apple.quarantine mp4-downloader-macos
```

## CLI Installation

Windows:

```powershell
iwr -useb https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
```

Linux/macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.sh | bash
```

After installing, open a new terminal if needed.

Uninstall:

```powershell
iwr -useb https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.sh | bash
```

## CLI Usage

Download with the interactive quality menu:

```bash
vd "https://www.youtube.com/watch?v=..."
```

Download multiple links:

```bash
vd "https://www.youtube.com/watch?v=..." "https://www.youtube.com/watch?v=..."
```

Skip the quality menu:

```bash
vd "https://www.youtube.com/watch?v=..." --quality 720p
vd "https://www.youtube.com/watch?v=..." --quality mp3
```

Use another folder once:

```bash
vd "https://www.youtube.com/watch?v=..." --folder "$HOME/Videos"
```

Settings and qualities:

```bash
vd settings
vd settings --folder "$HOME/Videos"
vd qualities
```

## Development

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run from source:

```bash
python run.py
```

Build GUI locally:

```bash
./build-linux-gui.sh
./build-macos-gui.sh
```

Windows:

```powershell
.\build-windows-gui.ps1
```

## Notes

The app uses `yt-dlp`. Some YouTube videos may fail when YouTube requires login, cookies, or bot verification. Running the app locally on your own PC is usually more reliable than running it on a VPS.
