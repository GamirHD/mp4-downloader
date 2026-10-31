# Video Downloader (`vd`)

Download videos from a link as **MP4** or **MP3** – from YouTube and many other sites, including
pages with their own video player or a login (e.g. course platforms, university servers).
Comes as a window app and as the command `vd`.

**Deutsch:** [README.de.md](README.de.md)

```powershell
vd "https://www.youtube.com/watch?v=..."
```

## Install

One command installs the window app **and** `vd`:

**Windows** (PowerShell) – or download and run
[`mp4-downloader-setup.exe`](https://github.com/GamirHD/mp4-downloader/releases/latest/download/mp4-downloader-setup.exe):

```powershell
irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
```

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.sh | bash
```

Afterwards you find **Video Downloader** in the Start menu / app menu / Applications folder, and the
command `vd` in every **new** terminal. Windows needs nothing else (ffmpeg is installed automatically);
Linux and macOS need Python 3 and ffmpeg. Update later with `vd update`.

## Using the command line

| Command | What happens |
| --- | --- |
| `vd "LINK"` | Download the video as MP4 (default: up to 1080p) |
| `vd -a "LINK"` | Audio only as MP3 |
| `vd -q 720p "LINK"` | Other quality: `best`, `1080p`, `720p`, `480p`, `mp3` |
| `vd "LINK1" "LINK2"` | Several videos one after another |
| `vd --playlist "LINK"` | A whole playlist |
| `vd -f "D:\Videos" "LINK"` | Into another folder |

Videos go to your **Downloads** folder. Change the defaults:

```powershell
vd settings -f "D:\Videos" -q 720p
vd settings --language de      # Deutsch / --language en for English
```

More: `vd history` (recent downloads), `vd update`, `vd --help`.

## Window app

Paste links, pick quality and folder, click **Download**. The language can be switched at the top
right, saved logins are managed under **Logins...**. It uses the same settings as `vd`.

## Pages with a login

Just enter the link as usual. If the page needs a login, vd asks:

```
example.com probably needs a login. Log in now? [Y/n]
```

Press **Enter**: a browser window opens (your default browser if it is Chromium-based, e.g. Brave or
Chrome – otherwise Edge). Log in, close the window, and the download starts again. The window uses its
own profile; your normal browser logins are not touched. The login is saved per site and used
automatically next time.

Some sites (e.g. university servers) ask for **user name and password** directly instead of showing
a login page. Then vd asks for them in the terminal (the password stays hidden). They are only sent to
that one site and stored encrypted for your Windows account.

```powershell
vd login            # list sites with a saved login
vd login "LINK"     # log in beforehand
vd logout SITE      # delete the login of one site (without SITE: all)
```

**Not possible:** copy-protected videos (DRM), e.g. Netflix, Disney+ or Prime Video – not even with a
login. vd tells you right away.

## Uninstall

Windows: *Settings → Apps → Video Downloader → Uninstall* (removes the app and `vd`).

Linux/macOS: `curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.sh | bash`

## For developers

```bash
python -m pip install -e .
python -m unittest
```

`build-windows.ps1` builds the Windows installer (PyInstaller + Inno Setup). Every pull request builds
it on a Windows machine at GitHub and tests install, `vd` and uninstall; Linux and macOS test
`install.sh`. Releases are created automatically when a new `version` in `pyproject.toml` reaches
`main` (optional notes in `.github/release-notes/vX.Y.Z.md`). Texts live in `i18n.py` (English and
German).
