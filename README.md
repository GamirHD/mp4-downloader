# mp4-downloader

Desktop app for downloading supported video links as MP4.

## Features

- Paste a video link
- Select quality: best, 1080p, 720p, 480p, or small
- Choose a download folder
- Download as MP4 with progress and status output
- Clearer messages when YouTube blocks a link or asks for cookies/login

## Requirements

- Python 3.10 or newer
- ffmpeg installed and available in `PATH`

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Run:

```bash
python run.py
```

## Notes

The app uses `yt-dlp`. Some YouTube videos may still fail when YouTube requires login, cookies, or bot verification. Running the app locally on your own PC is usually more reliable than running it on a VPS.
