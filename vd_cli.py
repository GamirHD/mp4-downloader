from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yt_dlp
except ImportError:  # pragma: no cover - handled at runtime
    yt_dlp = None


APP_NAME = "mp4-downloader"
__version__ = "0.8.20"
QUALITY_OPTIONS = {
    "best": ("Beste Qualitaet", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best", "mp4"),
    "1080p": ("1080p", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080]", "mp4"),
    "720p": ("720p", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]", "mp4"),
    "480p": ("480p", "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]", "mp4"),
    "mp3": ("MP3", "bestaudio/best", "mp3"),
}
BROWSER_CHOICES = ("brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi")
MAX_HISTORY_ENTRIES = 100
TRAILING_URL_PUNCTUATION = ".,;:!?"
URL_CANDIDATE_PATTERN = re.compile(r"https?://[^\s,]+", re.IGNORECASE)
WRAPPING_BRACKETS = (("(", ")"), ("[", "]"), ("{", "}"))


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


def download_archive_path() -> Path:
    return config_dir() / "download-archive.txt"


def history_path() -> Path:
    return config_dir() / "history.json"


def clean_history_entry(entry: dict[str, Any]) -> dict[str, str] | None:
    url = entry.get("url")
    if not isinstance(url, str) or not url.strip():
        return None

    cleaned: dict[str, str] = {"url": url.strip()}
    for key, fallback in (
        ("downloaded_at", "?"),
        ("title", "Video"),
        ("quality", "?"),
        ("folder", "?"),
    ):
        value = entry.get(key)
        cleaned[key] = value.strip() if isinstance(value, str) and value.strip() else fallback
    return cleaned


def trim_url_suffix(value: str) -> str:
    url = value.strip().strip("<>").rstrip(TRAILING_URL_PUNCTUATION)
    while url:
        changed = False
        for opener, closer in WRAPPING_BRACKETS:
            if url.endswith(closer) and url.count(closer) > url.count(opener):
                url = url[:-1].rstrip(TRAILING_URL_PUNCTUATION)
                changed = True
                break
        if not changed:
            return url
    return url


def extract_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_CANDIDATE_PATTERN.finditer(text):
        url = trim_url_suffix(match.group(0))
        if not url or url in seen:
            continue
        urls.append(url)
        seen.add(url)
    return urls


def normalize_url_args(values: list[str]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for value in values:
        for url in extract_urls_from_text(value):
            if url in seen:
                continue
            urls.append(url)
            seen.add(url)
    return urls


def no_urls_found_message() -> str:
    return "Kein unterstuetzter Link erkannt. Bitte eine URL mit http:// oder https:// einfuegen."


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "yes", "1", "on"}:
            return True
        if text in {"false", "no", "0", "off"}:
            return False
    return default


def load_settings() -> dict[str, Any]:
    defaults = {"download_dir": str(default_download_dir()), "use_download_archive": False}
    path = config_path()
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    download_dir = data.get("download_dir")
    if not isinstance(download_dir, str) or not download_dir.strip():
        download_dir = defaults["download_dir"]
    return {
        "download_dir": download_dir,
        "use_download_archive": _coerce_bool(
            data.get("use_download_archive", defaults["use_download_archive"]),
            defaults["use_download_archive"],
        ),
    }


def save_settings(settings: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def load_history() -> list[dict[str, Any]]:
    path = history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    entries: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        cleaned = clean_history_entry(entry)
        if cleaned is not None:
            entries.append(cleaned)
    return entries


def save_history(entries: list[dict[str, Any]]) -> None:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_entries = []
    for entry in entries:
        cleaned = clean_history_entry(entry)
        if cleaned is not None:
            cleaned_entries.append(cleaned)
    path.write_text(json.dumps(cleaned_entries[:MAX_HISTORY_ENTRIES], indent=2), encoding="utf-8")


def clear_history() -> None:
    path = history_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return


def add_history_entry(
    url: str,
    *,
    title: str,
    quality_key: str,
    folder: Path,
) -> None:
    entry = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": url,
        "title": title,
        "quality": quality_key,
        "folder": str(folder),
    }
    entries = [item for item in load_history() if item.get("url") != url]
    save_history([entry, *entries])


def format_history_timestamp(value: str) -> str:
    text = value.strip()
    if not text or text == "?":
        return "?"
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return text
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone().strftime("%Y-%m-%d %H:%M")


def friendly_error(raw_error: str) -> str:
    text = raw_error.strip()
    lower = text.lower()
    if "sign in to confirm" in lower or "bot" in lower or "cookies" in lower:
        return (
            "YouTube blockiert diesen Link oder verlangt eine Browser-Session. "
            "Versuche es mit Browser-Cookies, z. B. `--cookies-from-browser firefox`, "
            "oder waehle in der GUI den passenden Browser aus."
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
    use_download_archive: bool = False,
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
    if use_download_archive:
        archive_path = download_archive_path()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        options["download_archive"] = str(archive_path)
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
    use_download_archive: bool = False,
) -> dict[str, Any] | None:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp ist nicht installiert. Fuehre zuerst `python -m pip install .` aus.")

    folder.mkdir(parents=True, exist_ok=True)
    options = build_ydl_options(
        quality_key,
        folder,
        allow_playlist=allow_playlist,
        cookies_from_browser=cookies_from_browser,
        use_download_archive=use_download_archive,
    )
    with yt_dlp.YoutubeDL(options) as downloader:
        return downloader.extract_info(url, download=True)


def history_command(args: argparse.Namespace) -> int:
    if args.clear:
        clear_history()
        print("Download-Verlauf geloescht.")
        return 0

    entries = load_history()
    if not entries:
        print("Noch keine erfolgreichen Downloads im Verlauf.")
        print(f"Verlauf-Datei: {history_path()}")
        return 0

    limit = max(1, args.limit)
    for index, entry in enumerate(entries[:limit], start=1):
        title = entry.get("title") or "Video"
        url = entry.get("url") or ""
        quality = entry.get("quality") or "?"
        folder = entry.get("folder") or "?"
        downloaded_at = entry.get("downloaded_at") or "?"
        print(f"{index}. {title}")
        print(f"   URL: {url}")
        print(f"   Qualitaet: {quality}  Ordner: {folder}")
        print(f"   Zeit: {format_history_timestamp(downloaded_at)}")
    print(f"Verlauf-Datei: {history_path()}")
    return 0

def settings_command(args: argparse.Namespace) -> int:
    settings = load_settings()
    changed = False
    if args.folder:
        folder = Path(args.folder).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        settings["download_dir"] = str(folder)
        changed = True
        print(f"Downloadordner gespeichert: {folder}")
    if args.archive is not None:
        settings["use_download_archive"] = args.archive
        changed = True
        state = "aktiviert" if args.archive else "deaktiviert"
        print(f"Download-Archiv {state}.")

    if changed:
        save_settings(settings)
        return 0

    if not can_use_interactive_menu():
        print(f"Settings-Datei: {config_path()}")
        print(f"Downloadordner: {settings['download_dir']}")
        print(f"Download-Archiv: {'aktiviert' if settings['use_download_archive'] else 'deaktiviert'}")
        print(f"Archiv-Datei: {download_archive_path()}")
        return 0

    while True:
        current_folder = Path(settings["download_dir"]).expanduser()
        archive_state = "an" if settings["use_download_archive"] else "aus"
        selected = select_menu(
            f"Settings\nDownloadordner: {current_folder}\nDownload-Archiv: {archive_state}",
            ["Change Directory", "Toggle Download Archive", "Show Settings File", "Exit"],
        )
        if selected is None or selected == 3:
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
            settings["use_download_archive"] = not settings["use_download_archive"]
            save_settings(settings)
            state = "aktiviert" if settings["use_download_archive"] else "deaktiviert"
            print(f"Download-Archiv {state}.")
            pause()
            continue
        if selected == 2:
            print(f"Settings-Datei: {config_path()}")
            print(f"Downloadordner: {settings['download_dir']}")
            print(f"Download-Archiv: {'aktiviert' if settings['use_download_archive'] else 'deaktiviert'}")
            print(f"Archiv-Datei: {download_archive_path()}")
            pause()
    return 0


def qualities_command() -> int:
    for key, (label, _, _) in QUALITY_OPTIONS.items():
        print(f"{key:6} {label}")
    return 0


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("muss eine positive Zahl sein") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("muss eine positive Zahl sein")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vd",
        description="Video per Link als MP4 oder MP3 herunterladen.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
    archive_group = parser.add_mutually_exclusive_group()
    archive_group.add_argument(
        "--archive",
        action="store_true",
        dest="archive",
        help="Bereits heruntergeladene Videos ueberspringen und im Download-Archiv merken",
    )
    archive_group.add_argument(
        "--no-archive",
        action="store_false",
        dest="archive",
        help="Download-Archiv fuer diesen Download ausschalten",
    )
    parser.set_defaults(archive=None)
    return parser

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "history":
        history_parser = argparse.ArgumentParser(prog="vd history", description="Erfolgreiche Downloads anzeigen.")
        history_parser.add_argument("--limit", "-n", type=positive_int, default=20, help="Maximale Anzahl Eintraege")
        history_parser.add_argument("--clear", action="store_true", help="Download-Verlauf loeschen")
        return history_command(history_parser.parse_args(argv[1:]))
    if argv and argv[0] == "settings":
        settings_parser = argparse.ArgumentParser(prog="vd settings", description="Downloadordner anzeigen oder aendern.")
        settings_parser.add_argument("--folder", "-f", help="Neuer Standard-Downloadordner")
        archive_group = settings_parser.add_mutually_exclusive_group()
        archive_group.add_argument("--archive", action="store_true", dest="archive", help="Download-Archiv standardmaessig aktivieren")
        archive_group.add_argument("--no-archive", action="store_false", dest="archive", help="Download-Archiv standardmaessig deaktivieren")
        settings_parser.set_defaults(archive=None)
        return settings_command(settings_parser.parse_args(argv[1:]))
    if argv and argv[0] == "qualities":
        return qualities_command()

    parser = build_parser()
    args = parser.parse_args(argv)
    urls = normalize_url_args(args.urls)
    if not urls:
        parser.print_help()
        print()
        if args.urls:
            print(no_urls_found_message())
            print()
        print("Weitere Befehle:")
        print("  vd settings              Settings-Menue oeffnen")
        print("  vd settings --folder PFAD Downloadordner aendern")
        print("  vd history               Download-Verlauf anzeigen")
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
    use_download_archive = bool(settings.get("use_download_archive")) if args.archive is None else args.archive
    if use_download_archive:
        print(f"Download-Archiv: {download_archive_path()}")
    if len(urls) > 1:
        print(f"Links: {len(urls)}")

    failures = 0
    for index, url in enumerate(urls, start=1):
        if len(urls) > 1:
            print()
            print(f"[{index}/{len(urls)}] {url}")
        try:
            info = download(
                url,
                quality_key,
                folder,
                allow_playlist=args.playlist,
                cookies_from_browser=args.cookies_from_browser,
                use_download_archive=use_download_archive,
            )
            title = info.get("title", "Video") if isinstance(info, dict) else "Video"
            add_history_entry(url, title=title, quality_key=quality_key, folder=folder)
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            failures += 1
            print(f"Fehler: {friendly_error(str(exc))}", file=sys.stderr)

    if failures:
        print(f"Fertig mit Fehlern: {failures} von {len(urls)} fehlgeschlagen.", file=sys.stderr)
        return 1

    print("Download fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
