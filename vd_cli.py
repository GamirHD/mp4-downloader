from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import yt_dlp
except ImportError:  # pragma: no cover - handled at runtime
    yt_dlp = None


APP_NAME = "mp4-downloader"
QUALITY_OPTIONS = {
    "best": ("Beste Qualitaet", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best"),
    "1080p": ("1080p", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080]"),
    "720p": ("720p", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]"),
    "480p": ("480p", "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]"),
    "small": ("Audio + Video klein", "worst[ext=mp4]/worst"),
}


def default_download_dir() -> Path:
    return Path.home() / "Downloads"


def config_dir() -> Path:
    if os.name == "nt":
        root = os.environ.get("APPDATA")
        if root:
            return Path(root) / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def config_path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {"download_dir": str(default_download_dir())}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"download_dir": str(default_download_dir())}
    if not isinstance(data, dict):
        return {"download_dir": str(default_download_dir())}
    return {"download_dir": data.get("download_dir") or str(default_download_dir())}


def save_settings(settings: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def friendly_error(raw_error: str) -> str:
    text = raw_error.strip()
    lower = text.lower()
    if "sign in to confirm" in lower or "bot" in lower or "cookies" in lower:
        return (
            "YouTube blockiert diesen Link oder verlangt eine Browser-Session. "
            "Teste ein anderes Video oder versuche es spaeter erneut."
        )
    if "ffmpeg" in lower:
        return "ffmpeg fehlt oder wurde nicht gefunden. Installiere ffmpeg und starte das Terminal neu."
    if "unsupported url" in lower:
        return "Dieser Link wird nicht unterstuetzt. Bitte pruefe die URL."
    return text


def choose_quality() -> str:
    keys = list(QUALITY_OPTIONS)
    print("Aufloesung auswaehlen:")
    for index, key in enumerate(keys, start=1):
        print(f"  {index}. {QUALITY_OPTIONS[key][0]}")

    while True:
        choice = input("Auswahl [1]: ").strip()
        if not choice:
            return keys[0]
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(keys):
                return keys[number - 1]
        if choice.lower() in QUALITY_OPTIONS:
            return choice.lower()
        print("Bitte eine gueltige Nummer oder Qualitaet eingeben.")


def download(url: str, quality_key: str, folder: Path) -> None:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp ist nicht installiert. Fuehre zuerst `python -m pip install .` aus.")

    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = shutil.which("ffmpeg")
    _, format_selector = QUALITY_OPTIONS[quality_key]

    options: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": str(folder / "%(title).200s [%(id)s].%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
    }
    if ffmpeg_path:
        options["ffmpeg_location"] = os.path.dirname(ffmpeg_path)

    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([url])


def settings_command(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.folder:
        folder = Path(args.folder).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        settings["download_dir"] = str(folder)
        save_settings(settings)
        print(f"Downloadordner gespeichert: {folder}")
        return 0

    print(f"Settings-Datei: {config_path()}")
    print(f"Downloadordner: {settings['download_dir']}")
    return 0


def qualities_command() -> int:
    for key, (label, _) in QUALITY_OPTIONS.items():
        print(f"{key:6} {label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vd",
        description="Video per Link als MP4 herunterladen.",
    )
    parser.add_argument("url", nargs="?", help="Video-Link, z. B. ein YouTube-Link")
    parser.add_argument("--quality", "-q", choices=list(QUALITY_OPTIONS), help="Qualitaet direkt auswaehlen")
    parser.add_argument("--folder", "-f", help="Nur fuer diesen Download einen anderen Ordner verwenden")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "settings":
        settings_parser = argparse.ArgumentParser(prog="vd settings", description="Downloadordner anzeigen oder aendern.")
        settings_parser.add_argument("--folder", "-f", help="Neuer Standard-Downloadordner")
        return settings_command(settings_parser.parse_args(argv[1:]))
    if argv and argv[0] == "qualities":
        return qualities_command()

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.url:
        parser.print_help()
        print()
        print("Weitere Befehle:")
        print("  vd settings              Downloadordner anzeigen")
        print("  vd settings --folder PFAD Downloadordner aendern")
        print("  vd qualities             Qualitaeten anzeigen")
        return 2

    settings = load_settings()
    folder = Path(args.folder or settings["download_dir"]).expanduser()
    quality_key = args.quality or choose_quality()

    print(f"Zielordner: {folder}")
    print(f"Qualitaet: {QUALITY_OPTIONS[quality_key][0]}")

    try:
        download(args.url, quality_key, folder)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"Fehler: {friendly_error(str(exc))}", file=sys.stderr)
        return 1

    print("Download fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
