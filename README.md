# mp4-downloader

Desktop and console app for downloading supported video links as MP4 or MP3.

## Features

- Paste a video link
- Select quality: best, 1080p, 720p, 480p, or MP3
- Choose a download folder
- Download as MP4 or MP3 with progress and status output
- Console command: `vd <link>`
- Windows GUI executable in GitHub releases
- Arrow-key terminal menus for quality and settings
- Saved default download folder with `vd settings`
- GUI uses and updates the same saved default download folder
- GUI button for opening the current download folder
- GUI button for clearing the status log
- Windows folder picker for changing the default download folder
- Clearer messages when YouTube blocks a link or asks for cookies/login

## Requirements

- Python 3.10 or newer
- ffmpeg installed and available in `PATH`

## Console usage

Install with PowerShell:

```powershell
iwr -useb https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
```

After installing, close the terminal and open a new CMD or PowerShell window.

Uninstall:

```powershell
iwr -useb https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.ps1 | iex
```

Install from a downloaded project folder:

```cmd
python -m pip install .
```

After that you can use it from CMD or PowerShell:

```cmd
vd "https://www.youtube.com/watch?v=..."
```

The command asks for the quality or MP3, then starts the download. By default it saves into your Windows `Downloads` folder.
Use the arrow keys to choose a quality and press Enter.

Open settings:

```cmd
vd settings
```

Choose `Change Directory` to open the Windows folder picker and save a new default download folder.

Change the default download folder:

```cmd
vd settings --folder "C:\Users\Kadir\Downloads\Videos"
```

Download once into a different folder:

```cmd
vd "https://www.youtube.com/watch?v=..." --folder "C:\Users\Kadir\Desktop"
```

Skip the quality question:

```cmd
vd "https://www.youtube.com/watch?v=..." --quality 720p
```

Download audio as MP3:

```cmd
vd "https://www.youtube.com/watch?v=..." --quality mp3
```

Available qualities:

```cmd
vd qualities
```

## Desktop usage

For normal Windows use, download `mp4-downloader.exe` from the latest GitHub release and double-click it.
No CMD in the project folder is needed.

The GUI still needs `ffmpeg` available in `PATH` for merging MP4 files and converting MP3 audio.

Build the Windows GUI executable locally:

```powershell
.\build-windows-gui.ps1
```

The executable will be created at:

```text
dist\mp4-downloader.exe
```

Run from source:

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run:

```bash
python run.py
```

## Notes

The app uses `yt-dlp`. Some YouTube videos may still fail when YouTube requires login, cookies, or bot verification. Running the app locally on your own PC is usually more reliable than running it on a VPS.
