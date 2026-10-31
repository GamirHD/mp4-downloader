from __future__ import annotations

import argparse
import contextlib
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

from browser_login import (
    BrowserLoginError,
    cookies_to_netscape,
    delete_saved_login,
    has_saved_login,
    interactive_login,
    saved_cookies_for,
)
from cookie_input import (
    CookieInputError,
    clear_clipboard,
    cookies_text_to_netscape,
    read_clipboard_text,
    temporary_cookie_file,
)
from page_extractor import EmbeddedMedia, find_embedded_media, referer_headers


APP_NAME = "mp4-downloader"
__version__ = "0.9.3"
QUALITY_OPTIONS = {
    "best": ("Beste Qualität", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best", "mp4"),
    "1080p": ("Bis 1080p", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080]", "mp4"),
    "720p": ("Bis 720p", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]", "mp4"),
    "480p": ("Bis 480p", "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]", "mp4"),
    "mp3": ("Nur Audio (MP3)", "bestaudio/best", "mp3"),
}
EMBED_FALLBACK_ERROR_HINTS = ("unsupported url", "no video formats", "unable to extract", "no suitable")
BROWSER_CHOICES = ("brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi")
MAX_HISTORY_ENTRIES = 100
TRAILING_URL_PUNCTUATION = ".,;:!?"
URL_CANDIDATE_PATTERN = re.compile(
    r"(?<![@\w.-])(?:https?://)?(?:www\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+(?:/[^\s,]*)?",
    re.IGNORECASE,
)
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


def login_profile_dir() -> Path:
    return config_dir() / "browser-profile"


def saved_login_cookie_text(url: str, *, log: Any = print) -> str | None:
    """Cookies for ``url`` from the login saved with `vd login`, or None."""
    profile_dir = login_profile_dir()
    if not has_saved_login(profile_dir):
        return None
    try:
        cookies = saved_cookies_for(url, profile_dir)
    except BrowserLoginError as exc:
        log(f"Gespeicherter Login nicht nutzbar: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - never block a download because of this
        log(f"Gespeicherter Login konnte nicht gelesen werden: {exc}")
        return None
    if not cookies:
        return None
    log(f"Gespeicherter Login wird verwendet ({len(cookies)} Cookies).")
    return cookies_to_netscape(cookies)


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
    url = value.strip()
    while url:
        cleaned = url.strip("<>").rstrip(TRAILING_URL_PUNCTUATION)
        if cleaned == url:
            break
        url = cleaned
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


def normalize_url_candidate(value: str) -> str:
    url = trim_url_suffix(value)
    if url and not re.match(r"https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    return url


def extract_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_CANDIDATE_PATTERN.finditer(text):
        url = normalize_url_candidate(match.group(0))
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
    return "Kein unterstützter Link erkannt. Bitte eine URL mit http:// oder https:// einfügen."


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
    defaults = {"download_dir": str(default_download_dir()), "use_download_archive": False, "cookies_from_browser": None, "cookies_from_clipboard": False}
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
    cookies_from_browser = data.get("cookies_from_browser")
    if cookies_from_browser not in BROWSER_CHOICES:
        cookies_from_browser = None
    return {
        "download_dir": download_dir,
        "use_download_archive": _coerce_bool(
            data.get("use_download_archive", defaults["use_download_archive"]),
            defaults["use_download_archive"],
        ),
        "cookies_from_browser": cookies_from_browser,
        "cookies_from_clipboard": _coerce_bool(data.get("cookies_from_clipboard", False), False),
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
    if "kein eingebettetes video" in lower:
        return text
    if "drm" in lower and "dpapi" not in lower:
        return "Dieses Video ist kopiergeschuetzt (DRM) und kann nicht heruntergeladen werden."
    if "dpapi" in lower or "could not copy chrome cookie database" in lower:
        return (
            "Die Browser-Cookies koennen nicht gelesen werden (Chrome/Brave/Edge sperren das unter Windows). "
            "Exportiere stattdessen eine cookies.txt mit der Erweiterung \"Get cookies.txt LOCALLY\" "
            "und nutze `--cookies PFAD\\zur\\cookies.txt`."
        )
    if "sign in to confirm" in lower or "bot" in lower or "cookies" in lower:
        return (
            "YouTube blockiert diesen Link oder verlangt eine Browser-Session. "
            "Versuche es in der CLI mit Browser-Cookies, z. B. `--cookies-from-browser firefox`."
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
    cookie_file: str | None = None,
    referer: str | None = None,
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
    if cookie_file:
        options["cookiefile"] = str(Path(cookie_file).expanduser())
    if referer:
        options["http_headers"] = referer_headers(referer)
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


def should_try_embedded_media(error_text: str) -> bool:
    lower = error_text.lower()
    if "drm" in lower:
        return False
    return any(hint in lower for hint in EMBED_FALLBACK_ERROR_HINTS)


def embedded_media_options(base_options: dict[str, Any], media: EmbeddedMedia) -> dict[str, Any]:
    """Same options, but send the page as Referer and name the file after the page."""
    options = dict(base_options)
    headers = dict(options.get("http_headers") or {})
    headers.update(media.referer_headers)
    options["http_headers"] = headers
    options["noplaylist"] = True
    if media.title:
        from yt_dlp.utils import sanitize_filename

        outtmpl = base_options["outtmpl"]
        if isinstance(outtmpl, dict):
            outtmpl = outtmpl.get("default", "")
        folder = Path(str(outtmpl)).parent
        safe_title = sanitize_filename(media.title)[:200].replace("%", "%%") or "Video"
        options["outtmpl"] = str(folder / f"{safe_title}.%(ext)s")
    return options


def download_url(
    url: str,
    options: dict[str, Any],
    *,
    log: Any = print,
    search_embedded: bool = True,
    debug_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Download ``url``; for unknown pages look for an embedded video stream."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp ist nicht installiert. Fuehre zuerst `python -m pip install .` aus.")

    # yt-dlp rewrites the options dict it gets, so keep the original untouched.
    with yt_dlp.YoutubeDL(dict(options)) as downloader:
        try:
            return downloader.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            if not search_embedded or not should_try_embedded_media(str(exc)):
                raise
            log("Diese Seite wird nicht direkt unterstuetzt. Suche nach einem eingebetteten Video...")
            media = find_embedded_media(downloader, url, debug_dir=debug_dir, log=log)

    if media is None or not media.media_urls:
        raise RuntimeError(
            "Kein eingebettetes Video auf der Seite gefunden. Falls die Seite einen Login braucht, "
            "waehle deinen Browser fuer den Login aus (CLI: --cookies-from-browser) "
            "oder kopiere die .m3u8-Adresse aus den Entwicklertools (F12 > Netzwerk)."
        )

    media_options = embedded_media_options(options, media)
    last_error: Exception | None = None
    for candidate in media.media_urls:
        log(f"Lade eingebettetes Video: {candidate.split('?', 1)[0]}")
        try:
            with yt_dlp.YoutubeDL(dict(media_options)) as downloader:
                info = downloader.extract_info(candidate, download=True)
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            if "drm" in str(exc).lower():
                break
            continue
        if isinstance(info, dict) and media.title:
            info["title"] = media.title
        return info
    assert last_error is not None
    raise last_error


def download(
    url: str,
    quality_key: str,
    folder: Path,
    *,
    allow_playlist: bool = False,
    cookies_from_browser: str | None = None,
    cookie_file: str | None = None,
    referer: str | None = None,
    use_download_archive: bool = False,
    debug: bool = False,
) -> dict[str, Any] | None:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp ist nicht installiert. Fuehre zuerst `python -m pip install .` aus.")

    folder.mkdir(parents=True, exist_ok=True)
    options = build_ydl_options(
        quality_key,
        folder,
        allow_playlist=allow_playlist,
        cookies_from_browser=cookies_from_browser,
        cookie_file=cookie_file,
        referer=referer,
        use_download_archive=use_download_archive,
    )
    return download_url(url, options, debug_dir=folder / "vd-debug" if debug else None)


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

def login_command(args: argparse.Namespace) -> int:
    urls = normalize_url_args([args.url])
    if not urls:
        print(no_urls_found_message(), file=sys.stderr)
        return 2
    try:
        count = interactive_login(urls[0], login_profile_dir())
    except BrowserLoginError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    if count:
        print(f"Login gespeichert ({count} Cookies). Ab jetzt reicht: vd \"LINK\"")
        return 0
    print("Es wurden keine Cookies fuer diese Seite gespeichert. Warst du eingeloggt?", file=sys.stderr)
    return 1


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
        help="Login/Cookies aus einem lokalen Browser verwenden, z. B. fuer Kursseiten oder YouTube-Blockaden",
    )
    parser.add_argument(
        "--cookies",
        metavar="DATEI",
        help="Cookies aus einer cookies.txt-Datei (Netscape-Format) verwenden",
    )
    parser.add_argument(
        "--cookies-from-clipboard",
        action="store_true",
        help=(
            "Cookies aus der Zwischenablage verwenden (cookies.txt-Text oder Cookie-Header). "
            "Sie werden nur temporaer genutzt, danach geloescht, und die Zwischenablage wird geleert"
        ),
    )
    parser.add_argument(
        "--no-saved-login",
        action="store_true",
        help="Den mit `vd login` gespeicherten Login fuer diesen Download nicht verwenden",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Diagnose speichern (Screenshot und Anfragen des Hintergrund-Browsers) im Ordner vd-debug",
    )
    parser.add_argument(
        "--referer",
        metavar="URL",
        help="Seite, auf der das Video eingebettet ist (fuer direkt kopierte .m3u8-Links)",
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
    if argv and argv[0] == "login":
        login_parser = argparse.ArgumentParser(
            prog="vd login",
            description="Einmal im Programm-Browser einloggen; danach nutzt vd den Login automatisch.",
        )
        login_parser.add_argument("url", help="Seite, auf der du dich einloggen willst, z. B. https://example.com")
        return login_command(login_parser.parse_args(argv[1:]))
    if argv and argv[0] == "logout":
        if delete_saved_login(login_profile_dir()):
            print("Gespeicherter Login geloescht.")
        else:
            print("Es war kein Login gespeichert.")
        return 0
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
        print("  vd login LINK            Einmal einloggen, danach automatisch mit Login laden")
        print("  vd logout                Gespeicherten Login loeschen")
        return 2

    settings = load_settings()
    folder = Path(args.folder or settings["download_dir"]).expanduser()
    quality_key = args.quality or choose_quality()

    cookies_from_browser = args.cookies_from_browser
    if not cookies_from_browser and not args.cookies and not args.cookies_from_clipboard:
        cookies_from_browser = settings.get("cookies_from_browser")

    print(f"Zielordner: {folder}")
    print(f"Qualitaet: {QUALITY_OPTIONS[quality_key][0]}")
    if cookies_from_browser:
        print(f"Cookies: {cookies_from_browser}")
    if args.cookies:
        print(f"Cookie-Datei: {args.cookies}")
    if args.playlist:
        print("Playlist-Modus: aktiviert")
    use_download_archive = bool(settings.get("use_download_archive")) if args.archive is None else args.archive
    if use_download_archive:
        print(f"Download-Archiv: {download_archive_path()}")
    if len(urls) > 1:
        print(f"Links: {len(urls)}")

    clipboard_cookies: str | None = None
    if args.cookies_from_clipboard:
        try:
            clipboard_cookies, cookie_count = cookies_text_to_netscape(read_clipboard_text(), urls[0])
        except CookieInputError as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 2
        print(f"Cookies aus der Zwischenablage: {cookie_count} (werden nicht gespeichert)")
        if clear_clipboard():
            print("Zwischenablage geleert.")

    failures = 0
    with contextlib.ExitStack() as stack:
        cookie_file = args.cookies
        if clipboard_cookies is not None:
            cookie_file = str(stack.enter_context(temporary_cookie_file(clipboard_cookies)))
        for index, url in enumerate(urls, start=1):
            if len(urls) > 1:
                print()
                print(f"[{index}/{len(urls)}] {url}")
            try:
                with contextlib.ExitStack() as url_stack:
                    url_cookie_file = cookie_file
                    if url_cookie_file is None and not cookies_from_browser and not args.no_saved_login:
                        saved = saved_login_cookie_text(url)
                        if saved:
                            url_cookie_file = str(url_stack.enter_context(temporary_cookie_file(saved)))
                    info = download(
                        url,
                        quality_key,
                        folder,
                        allow_playlist=args.playlist,
                        cookies_from_browser=cookies_from_browser,
                        cookie_file=url_cookie_file,
                        referer=args.referer,
                        use_download_archive=use_download_archive,
                        debug=args.debug,
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
