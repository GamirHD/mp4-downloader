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
    "best": ("Beste Qualitaet", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best", "mp4"),
    "1080p": ("1080p", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080]", "mp4"),
    "720p": ("720p", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]", "mp4"),
    "480p": ("480p", "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]", "mp4"),
    "mp3": ("MP3", "bestaudio/best", "mp3"),
}
BROWSER_CHOICES = ("brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi")


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


def build_ydl_options(
    quality_key: str,
    folder: Path,
    *,
    allow_playlist: bool = False,
    cookies_from_browser: str | None = None,
    progress_hooks: list[Any] | None = None,
    logger: Any | None = None,
) -> dict[str, Any]:
    ffmpeg_path = shutil.which("ffmpeg")
    _, format_selector, output_kind = QUALITY_OPTIONS[quality_key]

    options: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": str(folder / "%(title).200s [%(id)s].%(ext)s"),
        "noplaylist": not allow_playlist,
        "quiet": False,
        "no_warnings": False,
    }
    if output_kind == "mp4":
        options["merge_output_format"] = "mp4"
    if output_kind == "mp3":
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    if ffmpeg_path:
        options["ffmpeg_location"] = os.path.dirname(ffmpeg_path)
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)
    if progress_hooks:
        options["progress_hooks"] = progress_hooks
    if logger:
        options["logger"] = logger

    return options


def can_use_interactive_menu() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def read_key() -> str:
    if os.name == "nt":
        import msvcrt

        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            extended = msvcrt.getwch()
            if extended == "H":
                return "up"
            if extended == "P":
                return "down"
            return "other"
        if char in ("\r", "\n"):
            return "enter"
        if char == "\x1b":
            return "escape"
        return char.lower()

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = sys.stdin.read(1)
        if char == "\x1b":
            sequence = sys.stdin.read(2)
            if sequence == "[A":
                return "up"
            if sequence == "[B":
                return "down"
            return "escape"
        if char in ("\r", "\n"):
            return "enter"
        return char.lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def menu_lines(title: str, items: list[str], selected: int) -> list[str]:
    lines = title.splitlines()
    lines.append("")
    for index, item in enumerate(items):
        pointer = ">" if index == selected else " "
        lines.append(f"{pointer} {item}")
    lines.append("")
    lines.append("Pfeiltasten: auswaehlen  Enter: bestaetigen  Q/Esc: abbrechen")
    return lines


def render_menu(lines: list[str], previous_line_count: int) -> int:
    if previous_line_count:
        print(f"\033[{previous_line_count}F", end="")
    width = shutil.get_terminal_size(fallback=(80, 24)).columns
    clear_line = "\033[2K"
    output = []
    for line in lines:
        output.append(f"{clear_line}{line[:width]}")
    print("\n".join(output), end="\n", flush=True)
    return len(lines)


def select_menu(title: str, items: list[str], default_index: int = 0) -> int | None:
    if not items:
        return None

    selected = max(0, min(default_index, len(items) - 1))
    if not can_use_interactive_menu():
        print(title)
        for index, item in enumerate(items, start=1):
            print(f"  {index}. {item}")
        while True:
            try:
                choice = input(f"Auswahl [{selected + 1}]: ").strip()
            except EOFError:
                return selected
            if not choice:
                return selected
            if choice.isdigit():
                number = int(choice)
                if 1 <= number <= len(items):
                    return number - 1
            print("Bitte eine gueltige Nummer eingeben.")

    previous_line_count = 0
    print("\033[?25l", end="", flush=True)
    try:
        while True:
            previous_line_count = render_menu(menu_lines(title, items, selected), previous_line_count)

            key = read_key()
            if key == "up":
                selected = (selected - 1) % len(items)
            elif key == "down":
                selected = (selected + 1) % len(items)
            elif key == "enter":
                print("\033[?25h", end="", flush=True)
                return selected
            elif key in ("q", "escape"):
                print("\033[?25h", end="", flush=True)
                return None
    finally:
        print("\033[?25h", end="", flush=True)


def pause() -> None:
    if can_use_interactive_menu():
        input("Enter druecken...")


def choose_quality() -> str:
    keys = list(QUALITY_OPTIONS)
    labels = [QUALITY_OPTIONS[key][0] for key in keys]
    selected = select_menu("Aufloesung auswaehlen", labels)
    return keys[0 if selected is None else selected]


def choose_directory(current_folder: Path) -> Path | None:
    if os.name == "nt":
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(
                initialdir=str(current_folder),
                title="Downloadordner auswaehlen",
            )
            root.destroy()
            if selected:
                return Path(selected)
            return None
        except Exception as exc:  # noqa: BLE001 - tkinter availability depends on the Python install
            print(f"Explorer-Auswahl nicht moeglich: {exc}")

    entered = input(f"Neuer Downloadordner [{current_folder}]: ").strip()
    if not entered:
        return None
    return Path(entered).expanduser()


def download(
    url: str,
    quality_key: str,
    folder: Path,
    *,
    allow_playlist: bool = False,
    cookies_from_browser: str | None = None,
) -> None:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp ist nicht installiert. Fuehre zuerst `python -m pip install .` aus.")

    folder.mkdir(parents=True, exist_ok=True)
    options = build_ydl_options(
        quality_key,
        folder,
        allow_playlist=allow_playlist,
        cookies_from_browser=cookies_from_browser,
    )
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

    if not can_use_interactive_menu():
        print(f"Settings-Datei: {config_path()}")
        print(f"Downloadordner: {settings['download_dir']}")
        return 0

    while True:
        current_folder = Path(settings["download_dir"]).expanduser()
        selected = select_menu(
            f"Settings\nDownloadordner: {current_folder}",
            ["Change Directory", "Show Settings File", "Exit"],
        )
        if selected is None or selected == 2:
            return 0
        if selected == 0:
            folder = choose_directory(current_folder)
            if folder is None:
                print("Nicht geaendert.")
                pause()
                continue
            folder = folder.expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            settings["download_dir"] = str(folder)
            save_settings(settings)
            print(f"Downloadordner gespeichert: {folder}")
            pause()
            continue
        if selected == 1:
            print(f"Settings-Datei: {config_path()}")
            print(f"Downloadordner: {settings['download_dir']}")
            pause()
    return 0


def qualities_command() -> int:
    for key, (label, _, _) in QUALITY_OPTIONS.items():
        print(f"{key:6} {label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vd",
        description="Video per Link als MP4 oder MP3 herunterladen.",
    )
    parser.add_argument("urls", nargs="*", help="Ein oder mehrere Video-Links, z. B. YouTube-Links")
    parser.add_argument("--quality", "-q", choices=list(QUALITY_OPTIONS), help="Qualitaet direkt auswaehlen")
    parser.add_argument("--folder", "-f", help="Nur fuer diesen Download einen anderen Ordner verwenden")
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Playlist-Links komplett herunterladen statt nur das einzelne Video",
    )
    parser.add_argument(
        "--cookies-from-browser",
        choices=BROWSER_CHOICES,
        help="Cookies aus einem lokalen Browser verwenden, z. B. bei YouTube-Login-Blockaden",
    )
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
    if not args.urls:
        parser.print_help()
        print()
        print("Weitere Befehle:")
        print("  vd settings              Settings-Menue oeffnen")
        print("  vd settings --folder PFAD Downloadordner aendern")
        print("  vd qualities             Qualitaeten anzeigen")
        return 2

    settings = load_settings()
    folder = Path(args.folder or settings["download_dir"]).expanduser()
    quality_key = args.quality or choose_quality()

    print(f"Zielordner: {folder}")
    print(f"Qualitaet: {QUALITY_OPTIONS[quality_key][0]}")
    if args.cookies_from_browser:
        print(f"Cookies: {args.cookies_from_browser}")
    if args.playlist:
        print("Playlist-Modus: aktiviert")
    if len(args.urls) > 1:
        print(f"Links: {len(args.urls)}")

    failures = 0
    for index, url in enumerate(args.urls, start=1):
        if len(args.urls) > 1:
            print()
            print(f"[{index}/{len(args.urls)}] {url}")
        try:
            download(
                url,
                quality_key,
                folder,
                allow_playlist=args.playlist,
                cookies_from_browser=args.cookies_from_browser,
            )
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            failures += 1
            print(f"Fehler: {friendly_error(str(exc))}", file=sys.stderr)

    if failures:
        print(f"Fertig mit Fehlern: {failures} von {len(args.urls)} fehlgeschlagen.", file=sys.stderr)
        return 1

    print("Download fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
