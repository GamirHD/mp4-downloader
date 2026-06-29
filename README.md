# mp4-downloader

Desktop and console app for downloading supported video links as MP4.

## Features

- Paste a video link
- Select quality: best, 1080p, 720p, 480p, or small
- Choose a download folder
- Download as MP4 with progress and status output
- Console command: `vd <link>`
- Saved default download folder with `vd settings`
- Clearer messages when YouTube blocks a link or asks for cookies/login

## Requirements

- Python 3.10 or newer
- ffmpeg installed and available in `PATH`

## Console usage

Install the app from this folder:

```cmd
py -m pip install .
```

After that you can use it from CMD or PowerShell:

```cmd
vd "https://www.youtube.com/watch?v=..."
```

The command asks for the quality, then starts the download. By default it saves into your Windows `Downloads` folder.

Show settings:

```cmd
vd settings
```

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

Available qualities:

```cmd
vd qualities
```

## Desktop usage

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
