# mp4-downloader

Simple desktop and CLI app for downloading supported video links as MP4 or MP3.

## Features

- Download one or more video links as MP4 or MP3
- Optional playlist downloads when explicitly enabled
- Quality choices: best quality, up to 1080p, up to 720p, up to 480p, MP3 audio
- Windows/Linux/macOS GUI builds in GitHub releases
- Windows setup installer for the GUI
- CLI command: `vd "https://..."`
- Saved default download folder shared by GUI and CLI
- Clearer error messages for common YouTube blocks
- Optional CLI browser-cookie support for links that require your local login session
- Optional CLI download archive to skip videos that were already downloaded before
- GUI cancel button for stopping long or accidental downloads
- Cleaner GUI flow with separate link, options, and download log steps
- Refined GUI theme with calmer colors, clearer action buttons, and cleaner input/list areas
- High-DPI aware GUI rendering for sharper text and controls on scaled displays
- GUI download queue with add and selected-item removal
- GUI link input handles links separated by new lines, spaces, tabs, or commas
- GUI download start also uses a link that is still in the input field
- GUI paste trims common chat wrappers like `<...>` and trailing punctuation
- GUI and CLI explain when pasted text contains no supported link
- Shared download history for CLI and GUI
- Videos embedded in normal web pages (e.g. course platforms with their own player): paste the page link and the app finds the stream
- GUI browser-login choice for pages that require your login
- Login when needed: if a download fails because of a missing login, vd offers to open a browser window, saves the login per website and retries
- Login cookies from the clipboard, used only temporarily (no cookie file left in the download folder)

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

You can also paste a quoted block of links separated by new lines, spaces, tabs, or commas:

```bash
vd "https://www.youtube.com/watch?v=...
https://www.youtube.com/watch?v=..."
```

Skip the quality menu:

```bash
vd "https://www.youtube.com/watch?v=..." --quality 720p
vd "https://www.youtube.com/watch?v=..." --quality mp3
```

Use cookies from a local browser when a site requires your login session:

```bash
vd "https://www.youtube.com/watch?v=..." --cookies-from-browser firefox
vd "https://www.youtube.com/watch?v=..." --quality mp3 --cookies-from-browser chrome
```

### Videos embedded in web pages

Many sites (for example course platforms) use their own video player. You can paste the
link of the page itself; the app then searches for the embedded video:

1. yt-dlp tries the page directly (works for many known players such as Vimeo or Kaltura).
2. Otherwise the page HTML is searched for `.m3u8`, `.mpd` or `.mp4` streams and player iframes.
3. If the player builds the stream with JavaScript, the page is opened in a hidden browser
   and the stream request is recorded (needs Playwright, see below).

The page is sent as `Referer` and the file is named after the page title.

```bash
vd "https://example.com/kurse/mein-kurs/video-1/" --cookies-from-browser firefox
```

The easiest way for pages behind a login: just run `vd "LINK"`. If the download fails and a login
could help, vd asks whether you want to log in. A browser window opens, you log in, close the
window, and the download starts again. The login is saved per website and used automatically
next time. You can also log in beforehand or manage the saved logins:

```bash
vd login "https://example.com"   # log in beforehand
vd login --list                   # websites with a saved login
vd logout example.com             # remove the login of one website
vd logout                         # remove all saved logins
```

Use `--no-login-prompt` to never ask.

The login is stored only in the app settings folder (not in the download folder). In the GUI use
the "Einloggen…" button next to "Browser-Login". Websites usually keep you logged in for a few
weeks; when downloads stop working, run `vd login` again.

Alternatively, choose the browser you are logged in with (`--cookies-from-browser`,
or "Browser-Login" in the GUI). If reading the browser cookies fails (Chromium browsers on
Windows can block this), log in with Firefox or export a `cookies.txt` with a browser extension:

```bash
vd "https://example.com/kurse/mein-kurs/video-1/" --cookies cookies.txt
```

Or paste the cookies from the clipboard so that no cookie file is left behind. Copy them with
"Get cookies.txt LOCALLY" (Copy button) or copy the `cookie` request header from the developer
tools, then run:

```bash
vd "https://example.com/kurse/mein-kurs/video-1/" --cookies-from-clipboard
```

The cookies are only written to a private temporary file during the download, deleted afterwards,
and the clipboard is cleared. In the GUI choose "Aus Zwischenablage (cookies.txt)" under "Browser-Login".

Optional hidden-browser search for JavaScript players:

```bash
python -m pip install playwright
# only needed if neither Microsoft Edge nor Chrome is installed:
python -m playwright install chromium
```

You can also copy a stream link from the browser developer tools (F12 > Network, filter `m3u8`)
and pass the page as referer:

```bash
vd "https://cdn.example.com/.../master.m3u8?token=..." --referer "https://example.com/kurse/mein-kurs/video-1/"
```

If no video is found, run again with `--debug`: a screenshot and the list of requests of the
hidden browser are saved to `vd-debug` in the download folder. The hidden browser uses an
installed Microsoft Edge or Chrome when available.

DRM-protected (copy-protected) videos are not supported, even with a login - for example
Netflix, Disney+ or Prime Video. vd reports this instead of asking for a login.

Download a full playlist instead of only the linked video:

```bash
vd "https://www.youtube.com/playlist?list=..." --playlist
```

Skip videos that were already downloaded before:

```bash
vd "https://www.youtube.com/watch?v=..." --archive
vd "https://www.youtube.com/watch?v=..." --no-archive
vd settings --archive
vd settings --no-archive
```

Use another folder once:

```bash
vd "https://www.youtube.com/watch?v=..." --folder "$HOME/Videos"
```

Settings and qualities:

```bash
vd settings
vd settings --folder "$HOME/Videos"
vd history
vd qualities
vd --version
```

The CLI download archive and shared download history are stored next to the app settings.

## Development

Install dependencies:

```bash
# Windows: python
# Linux/macOS: python3
python3 -m pip install -r requirements.txt
```

Run from source:

```bash
python3 run.py
```

Run checks:

```bash
python3 -m py_compile mp4_downloader.py vd_cli.py run.py
python3 -m unittest -v
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

## Releases

Releases are created automatically: when a new `version` in `pyproject.toml` reaches `main`
and there is no release with that tag yet, GitHub Actions creates the release `vX.Y.Z` and
attaches the Windows, Linux and macOS builds. Optional release notes can be put in
`.github/release-notes/vX.Y.Z.md`; otherwise GitHub generates them from the merged pull requests.
Publishing a release manually on GitHub still works too.

## Notes

The app uses `yt-dlp`. Some YouTube videos may fail when YouTube requires login, cookies, or bot verification. Running the app locally on your own PC is usually more reliable than running it on a VPS.
