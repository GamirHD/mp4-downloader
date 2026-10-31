"""vd - Videos per Link als MP4 oder MP3 herunterladen."""

from __future__ import annotations

import argparse
import contextlib
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import yt_dlp
except ImportError:  # pragma: no cover - handled at runtime
    yt_dlp = None

from browser_login import (
    BrowserLoginError,
    cookies_to_netscape,
    delete_saved_login,
    delete_site_login,
    interactive_login,
    saved_cookies_for,
    saved_sites,
    site_of,
    temporary_cookie_file,
)
from page_extractor import EmbeddedMedia, find_embedded_media, referer_headers
from site_auth import (
    Credentials,
    credential_sites,
    delete_credentials,
    is_http_auth_error,
    basic_auth_header,
    load_credentials,
    save_credentials,
    site_key,
)

APP_NAME = "mp4-downloader"
__version__ = "1.3.1"
REPO_ZIP_URL = "https://github.com/GamirHD/mp4-downloader/archive/refs/heads/main.zip"
LATEST_RELEASE_API = "https://api.github.com/repos/GamirHD/mp4-downloader/releases/latest"
SETUP_URL = "https://github.com/GamirHD/mp4-downloader/releases/latest/download/mp4-downloader-setup.exe"

# Wistia and similar hosts offer the huge upload file as format "original";
# it is skipped unless nothing else exists.
_NOT_ORIGINAL = "[format_id!=original]"
QUALITY_OPTIONS = {
    "best": (
        "Beste Qualität",
        f"bv*[ext=mp4]{_NOT_ORIGINAL}+ba[ext=m4a]/b[ext=mp4]{_NOT_ORIGINAL}/bv*+ba/b",
        "mp4",
    ),
    "1080p": (
        "Bis 1080p",
        f"bv*[height<=1080][ext=mp4]{_NOT_ORIGINAL}+ba[ext=m4a]/b[height<=1080][ext=mp4]{_NOT_ORIGINAL}"
        "/bv*[height<=1080]+ba/b[height<=1080]/b",
        "mp4",
    ),
    "720p": (
        "Bis 720p",
        f"bv*[height<=720][ext=mp4]{_NOT_ORIGINAL}+ba[ext=m4a]/b[height<=720][ext=mp4]{_NOT_ORIGINAL}"
        "/bv*[height<=720]+ba/b[height<=720]/b",
        "mp4",
    ),
    "480p": (
        "Bis 480p",
        f"bv*[height<=480][ext=mp4]{_NOT_ORIGINAL}+ba[ext=m4a]/b[height<=480][ext=mp4]{_NOT_ORIGINAL}"
        "/bv*[height<=480]+ba/b[height<=480]/b",
        "mp4",
    ),
    "mp3": ("Nur Audio (MP3)", "bestaudio/best", "mp3"),
}
DEFAULT_QUALITY = "1080p"
EMBED_FALLBACK_ERROR_HINTS = ("unsupported url", "no video formats", "unable to extract", "no suitable")
LOGIN_ERROR_HINTS = (
    "login", "log in", "sign in", "signin", "anmeld", "einlogg", "cookies", "401", "403", "forbidden",
    "unauthorized", "private", "members", "premium", "subscri", "registered", "authenticat", "account",
    "kein eingebettetes video",
)
NO_LOGIN_HELP_HINTS = ("drm", "ffmpeg", "dpapi", "no space", "kein speicherplatz")
MAX_HISTORY_ENTRIES = 100
TRAILING_URL_PUNCTUATION = ".,;:!?"
URL_CANDIDATE_PATTERN = re.compile(
    r"(?<![@\w.-])(?:https?://)?(?:www\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+(?:/[^\s,]*)?",
    re.IGNORECASE,
)
WRAPPING_BRACKETS = (("(", ")"), ("[", "]"), ("{", "}"))


# --------------------------------------------------------------------------- paths & settings


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


def history_path() -> Path:
    return config_dir() / "history.json"


def login_profile_dir() -> Path:
    return config_dir() / "browser-profile"


def load_settings() -> dict[str, Any]:
    settings = {"download_dir": str(default_download_dir()), "quality": DEFAULT_QUALITY}
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    if not isinstance(data, dict):
        return settings
    if isinstance(data.get("download_dir"), str) and data["download_dir"].strip():
        settings["download_dir"] = data["download_dir"]
    if data.get("quality") in QUALITY_OPTIONS:
        settings["quality"] = data["quality"]
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {"download_dir": str(settings["download_dir"]), "quality": settings.get("quality", DEFAULT_QUALITY)}
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- history


def clean_history_entry(entry: dict[str, Any]) -> dict[str, str] | None:
    url = entry.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    cleaned: dict[str, str] = {"url": url.strip()}
    for key, fallback in (("downloaded_at", "?"), ("title", "Video"), ("quality", "?"), ("folder", "?")):
        value = entry.get(key)
        cleaned[key] = value.strip() if isinstance(value, str) and value.strip() else fallback
    return cleaned


def load_history() -> list[dict[str, Any]]:
    try:
        data = json.loads(history_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in (clean_history_entry(e) for e in data if isinstance(e, dict)) if entry]


def save_history(entries: list[dict[str, Any]]) -> None:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = [entry for entry in (clean_history_entry(e) for e in entries) if entry]
    path.write_text(json.dumps(cleaned[:MAX_HISTORY_ENTRIES], indent=2), encoding="utf-8")


def clear_history() -> None:
    with contextlib.suppress(FileNotFoundError):
        history_path().unlink()


def add_history_entry(url: str, *, title: str, quality_key: str, folder: Path) -> None:
    entry = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": url,
        "title": title,
        "quality": quality_key,
        "folder": str(folder),
    }
    save_history([entry, *[item for item in load_history() if item.get("url") != url]])


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


# --------------------------------------------------------------------------- links


def trim_url_suffix(value: str) -> str:
    url = value.strip()
    while url:
        cleaned = url.strip("<>").rstrip(TRAILING_URL_PUNCTUATION)
        if cleaned == url:
            break
        url = cleaned
    while url:
        for opener, closer in WRAPPING_BRACKETS:
            if url.endswith(closer) and url.count(closer) > url.count(opener):
                url = url[:-1].rstrip(TRAILING_URL_PUNCTUATION)
                break
        else:
            return url
    return url


def normalize_url_candidate(value: str) -> str:
    url = trim_url_suffix(value)
    if url and not re.match(r"https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    return url


def extract_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_CANDIDATE_PATTERN.finditer(text):
        url = normalize_url_candidate(match.group(0))
        if url and url not in urls:
            urls.append(url)
    return urls


def normalize_url_args(values: list[str]) -> list[str]:
    urls: list[str] = []
    for value in values:
        for url in extract_urls_from_text(value):
            if url not in urls:
                urls.append(url)
    return urls


def no_urls_found_message() -> str:
    return "Kein Link erkannt. Bitte eine Adresse wie https://... angeben."


# --------------------------------------------------------------------------- errors


def friendly_error(raw_error: str) -> str:
    text = raw_error.strip()
    while text.upper().startswith("ERROR:"):
        text = text[6:].strip()
    text = re.sub(r"^\[[\w:.-]+\]\s+[\w.-]+:\s+", "", text)
    lower = text.lower()
    if "kein eingebettetes video" in lower:
        return text
    if "drm" in lower and "dpapi" not in lower:
        return (
            "Dieses Video ist kopiergeschützt (DRM) und kann nicht heruntergeladen werden "
            "(z. B. Netflix, Disney+, Prime Video) - auch nicht mit Login."
        )
    if "ffmpeg" in lower:
        return "ffmpeg fehlt. Installiere es (Windows: winget install Gyan.FFmpeg) und öffne ein neues Terminal."
    if is_http_auth_error(lower):
        return "Benutzername oder Passwort fehlt oder ist falsch (HTTP 401)."
    if "sign in to confirm" in lower or "not a bot" in lower:
        return "YouTube verlangt einen Login. Logge dich mit `vd login https://www.youtube.com` ein."
    if "unsupported url" in lower:
        return "Dieser Link wird nicht unterstützt."
    if "http error 404" in lower:
        return "Die Seite wurde nicht gefunden (404). Bitte den Link prüfen."
    return text


def login_might_help(error_text: str) -> bool:
    """Guess whether logging in could fix a failed download."""
    lower = error_text.lower()
    if any(hint in lower for hint in NO_LOGIN_HELP_HINTS):
        return False
    return any(hint in lower for hint in LOGIN_ERROR_HINTS)


def should_try_embedded_media(error_text: str) -> bool:
    lower = error_text.lower()
    return "drm" not in lower and any(hint in lower for hint in EMBED_FALLBACK_ERROR_HINTS)


# --------------------------------------------------------------------------- yt-dlp options


class _SilentLogger:
    """yt-dlp talks a lot; vd shows its own short messages instead."""

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def build_ydl_options(
    quality_key: str,
    folder: Path,
    *,
    allow_playlist: bool = False,
    cookie_file: str | None = None,
    referer: str | None = None,
    progress_hooks: list[Any] | None = None,
    logger: Any | None = None,
) -> dict[str, Any]:
    _, format_selector, output_kind = QUALITY_OPTIONS[quality_key]
    options: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": str(folder / "%(title).200s.%(ext)s"),
        "noplaylist": not allow_playlist,
        "logger": logger or _SilentLogger(),
        "noprogress": True,
    }
    if output_kind == "mp4":
        options["merge_output_format"] = "mp4"
    else:
        options["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        options["ffmpeg_location"] = os.path.dirname(ffmpeg_path)
    if cookie_file:
        options["cookiefile"] = str(Path(cookie_file).expanduser())
    if referer:
        options["http_headers"] = referer_headers(referer)
    if progress_hooks:
        options["progress_hooks"] = progress_hooks
    return options


def embedded_media_options(base_options: dict[str, Any], media: EmbeddedMedia) -> dict[str, Any]:
    """Same options, but send the page as Referer and name the file after the page."""
    options = dict(base_options)
    options["http_headers"] = {**dict(options.get("http_headers") or {}), **media.referer_headers}
    options["noplaylist"] = True
    if media.title:
        from yt_dlp.utils import sanitize_filename

        outtmpl = base_options["outtmpl"]
        if isinstance(outtmpl, dict):
            outtmpl = outtmpl.get("default", "")
        safe_title = sanitize_filename(media.title)[:200].replace("%", "%%") or "Video"
        options["outtmpl"] = str(Path(str(outtmpl)).parent / f"{safe_title}.%(ext)s")
    return options


# --------------------------------------------------------------------------- downloading


def make_downloader(options: dict[str, Any], credentials: Credentials | None, site_url: str) -> Any:
    """A YoutubeDL that sends the HTTP login only with requests to the website of ``site_url``."""
    if credentials is None:
        return yt_dlp.YoutubeDL(options)

    from yt_dlp.networking import Request

    header = basic_auth_header(credentials)
    allowed = site_key(site_url)

    class AuthYoutubeDL(yt_dlp.YoutubeDL):
        def urlopen(self, req: Any) -> Any:
            if isinstance(req, str):
                req = Request(req)
            if site_key(req.url) == allowed and "Authorization" not in req.headers:
                req.headers["Authorization"] = header
            return super().urlopen(req)

    return AuthYoutubeDL(options)


def download_url(
    url: str,
    options: dict[str, Any],
    *,
    log: Callable[[str], None] = print,
    debug_dir: Path | None = None,
    credentials: Credentials | None = None,
) -> dict[str, Any] | None:
    """Download ``url``; for unknown pages look for an embedded video stream.

    ``credentials`` (HTTP login) are only sent to the website of ``url``.
    """
    if yt_dlp is None:
        raise RuntimeError("yt-dlp fehlt. Installiere vd neu.")

    # yt-dlp rewrites the options dict it gets, so keep the original untouched.
    with make_downloader(dict(options), credentials, url) as downloader:
        try:
            return downloader.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            if not should_try_embedded_media(str(exc)):
                raise
            log("Suche das Video auf der Seite...")
            media = find_embedded_media(downloader, url, debug_dir=debug_dir, credentials=credentials, log=log)

    if media is None or not media.media_urls:
        raise RuntimeError(
            "Kein eingebettetes Video auf der Seite gefunden. Falls die Seite einen Login braucht: "
            f"vd login \"{url}\""
        )

    media_options = embedded_media_options(options, media)
    last_error: Exception | None = None
    for candidate in media.media_urls:
        try:
            with make_downloader(dict(media_options), credentials, url) as downloader:
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


def saved_login_cookie_text(url: str) -> str | None:
    """Cookies for ``url`` from a saved login, or None."""
    cookies = saved_cookies_for(url, login_profile_dir())
    return cookies_to_netscape(cookies) if cookies else None


def run_download(
    url: str,
    quality_key: str,
    folder: Path,
    *,
    playlist: bool = False,
    cookie_file: str | None = None,
    referer: str | None = None,
    debug: bool = False,
    progress_hooks: list[Any] | None = None,
    logger: Any | None = None,
    log: Callable[[str], None] = print,
    ask: Callable[[str], bool] | None = None,
    ask_credentials: Callable[[str, bool], Credentials | None] | None = None,
) -> dict[str, Any] | None:
    """Download one link. Uses a saved login; offers a login when one seems to be missing.

    ``ask`` is called with a yes/no question; without it vd never opens a login window.
    ``ask_credentials(site, wrong)`` asks for user name and password (HTTP login).
    """
    folder.mkdir(parents=True, exist_ok=True)
    use_saved_login = cookie_file is None
    site = site_of(url)
    auth: list[Credentials | None] = [load_credentials(login_profile_dir(), url) if use_saved_login else None]

    def attempt() -> dict[str, Any] | None:
        with contextlib.ExitStack() as stack:
            used_cookie_file = cookie_file
            if use_saved_login:
                saved = saved_login_cookie_text(url)
                if saved:
                    used_cookie_file = str(stack.enter_context(temporary_cookie_file(saved)))
            options = build_ydl_options(
                quality_key,
                folder,
                allow_playlist=playlist,
                cookie_file=used_cookie_file,
                referer=referer,
                progress_hooks=progress_hooks,
                logger=logger,
            )
            return download_url(
                url, options, log=log, debug_dir=folder / "vd-debug" if debug else None, credentials=auth[0]
            )

    try:
        return attempt()
    except Exception as first_error:  # noqa: BLE001 - maybe a login helps
        if use_saved_login and is_http_auth_error(str(first_error)):
            return _retry_with_credentials(url, site, auth, attempt, ask_credentials, log, first_error)
        if not (use_saved_login and login_might_help(str(first_error))) or auth[0] is not None:
            raise
        if ask is None:
            raise RuntimeError(f"{friendly_error(str(first_error))}\nTipp: vd login \"{url}\"") from first_error
        if saved_cookies_for(url, login_profile_dir()):
            question = f"Der Login für {site} ist vielleicht abgelaufen. Neu einloggen?"
        else:
            question = f"{site} braucht vermutlich einen Login. Jetzt einloggen?"
        if not ask(question):
            raise
        log("Ein Browserfenster öffnet sich: einloggen und das Fenster danach schließen.")
        if not interactive_login(url, login_profile_dir(), log=lambda _text: None):
            raise RuntimeError("Es wurde kein Login gespeichert.") from first_error
        log(f"Login für {site} gespeichert. Neuer Versuch...")
        return attempt()


def _retry_with_credentials(
    url: str,
    site: str,
    auth: list[Credentials | None],
    attempt: Callable[[], dict[str, Any] | None],
    ask_credentials: Callable[[str, bool], Credentials | None] | None,
    log: Callable[[str], None],
    first_error: Exception,
) -> dict[str, Any] | None:
    """The website asks for user name and password (HTTP login, e.g. university servers)."""
    if ask_credentials is None:
        raise RuntimeError(f"{site} verlangt Benutzername und Passwort. Starte vd im Terminal, um sie einzugeben.") from first_error
    wrong = auth[0] is not None
    for _ in range(3):
        credentials = ask_credentials(site, wrong)
        if credentials is None:
            raise RuntimeError("Abgebrochen: keine Zugangsdaten eingegeben.") from first_error
        auth[0] = credentials
        try:
            info = attempt()
        except Exception as exc:  # noqa: BLE001 - wrong password? ask again
            if is_http_auth_error(str(exc)):
                wrong = True
                continue
            raise
        if save_credentials(login_profile_dir(), url, credentials):
            log(f"Zugangsdaten für {site} gespeichert (verschlüsselt).")
        return info
    raise RuntimeError("Benutzername oder Passwort falsch.") from first_error


def ask_credentials_console(site: str, wrong: bool) -> Credentials | None:
    if wrong:
        warn("Benutzername oder Passwort falsch.")
    say(f"{site} verlangt Benutzername und Passwort.")
    try:
        username = input("Benutzername: ").strip()
        if not username:
            return None
        password = getpass.getpass("Passwort (wird nicht angezeigt): ")
    except EOFError:
        return None
    return Credentials(username, password)


def downloaded_file(info: dict[str, Any] | None) -> str | None:
    if not isinstance(info, dict):
        return None
    for item in info.get("requested_downloads") or []:
        if isinstance(item, dict) and item.get("filepath"):
            return str(item["filepath"])
    return info.get("filepath") or info.get("_filename")


# --------------------------------------------------------------------------- console output


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask_yes_no(question: str, *, default: bool = True) -> bool:
    suffix = " [J/n] " if default else " [j/N] "
    try:
        answer = input(question + suffix).strip().lower()
    except EOFError:
        return False
    if not answer:
        return default
    return answer in {"j", "ja", "y", "yes"}


def format_size(num_bytes: float | None) -> str:
    if not num_bytes:
        return "?"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            text = f"{value:.0f}" if unit in ("B", "KB") else f"{value:.1f}"
            return f"{text.replace('.', ',')} {unit}"
        value /= 1024
    return "?"


def format_eta(seconds: float | None) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def display_name(filename: str) -> str:
    """"Title.f137.mp4.part" -> "Title" (the file is named after the video title)."""
    name = Path(filename).name if filename else ""
    for suffix in (".part", ".ytdl"):
        name = name.removesuffix(suffix)
    name = re.sub(r"(\.f[\w-]+)?\.\w{2,4}$", "", name)
    return name


class ConsoleProgress:
    """One updating progress line per file instead of yt-dlp's output."""

    def __init__(self, stream: Any = None) -> None:
        self.stream = stream or sys.stdout
        self.live = bool(getattr(self.stream, "isatty", lambda: False)())
        self.current: str | None = None
        self.line_open = False

    def _write_line(self, text: str) -> None:
        if not self.live:
            return
        width = shutil.get_terminal_size(fallback=(80, 24)).columns - 1
        self.stream.write("\r" + text[:width].ljust(width))
        self.stream.flush()
        self.line_open = True

    def end_line(self) -> None:
        if self.line_open:
            self.stream.write("\n")
            self.stream.flush()
            self.line_open = False

    def hook(self, data: dict[str, Any]) -> None:
        info = data.get("info_dict") or {}
        key = str(data.get("filename") or info.get("id") or "")
        if key != self.current:
            self.end_line()
            self.current = key
            part = " (Ton)" if info.get("vcodec") == "none" and info.get("acodec") not in (None, "none") else ""
            print(f"Lade: {display_name(key) or info.get('title') or 'Video'}{part}", file=self.stream, flush=True)
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes") or 0
            parts = []
            if total:
                parts.append(f"{min(done / total * 100, 100):5.1f} %".replace(".", ","))
                parts.append(f"{format_size(done)} von {format_size(total)}")
            else:
                parts.append(format_size(done))
            if data.get("speed"):
                parts.append(f"{format_size(data['speed'])}/s")
            if data.get("eta") is not None:
                parts.append(f"noch {format_eta(data['eta'])}")
            self._write_line("  " + "  ·  ".join(parts))
        elif data.get("status") == "finished":
            self._write_line(f"  100 %  ·  {format_size(data.get('total_bytes') or data.get('downloaded_bytes'))}")
            self.end_line()


def say(text: str) -> None:
    print(text, flush=True)


def warn(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- commands


def download_command(args: argparse.Namespace) -> int:
    urls = normalize_url_args(args.urls)
    if not urls:
        warn(no_urls_found_message())
        return 2

    settings = load_settings()
    folder = Path(args.folder or settings["download_dir"]).expanduser()
    quality_key = "mp3" if args.audio else (args.quality or settings["quality"])
    progress = ConsoleProgress()
    ask = ask_yes_no if is_interactive() else None

    failures = 0
    for index, url in enumerate(urls, start=1):
        if len(urls) > 1:
            say(f"\n[{index}/{len(urls)}] {url}")
        try:
            info = run_download(
                url,
                quality_key,
                folder,
                playlist=args.playlist,
                cookie_file=args.cookies,
                referer=args.referer,
                debug=args.debug,
                progress_hooks=[progress.hook],
                logger=None if not args.debug else _VerboseLogger(),
                log=lambda text: (progress.end_line(), say(text)),
                ask=ask,
                ask_credentials=ask_credentials_console if ask else None,
            )
        except KeyboardInterrupt:
            progress.end_line()
            warn("Abgebrochen.")
            return 130
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            progress.end_line()
            failures += 1
            warn(f"Fehler: {friendly_error(str(exc))}")
            continue
        progress.end_line()
        title = info.get("title", "Video") if isinstance(info, dict) else "Video"
        add_history_entry(url, title=title, quality_key=quality_key, folder=folder)
        say(f"Gespeichert: {downloaded_file(info) or folder}")

    if failures:
        if len(urls) > 1:
            warn(f"{failures} von {len(urls)} Downloads fehlgeschlagen.")
        return 1
    return 0


class _VerboseLogger:
    def debug(self, message: str) -> None:
        print(message)

    info = debug
    warning = debug

    def error(self, message: str) -> None:
        print(message, file=sys.stderr)


def login_command(args: argparse.Namespace) -> int:
    if not args.url:
        sites = sorted({site for site, _count in saved_sites(login_profile_dir())} | set(credential_sites(login_profile_dir())))
        if not sites:
            say('Noch keine Logins gespeichert. Einloggen mit: vd login "LINK"')
            return 0
        say("Gespeicherte Logins:")
        for site in sites:
            say(f"  {site}")
        say("Ausloggen mit: vd logout SEITE")
        return 0
    urls = normalize_url_args([args.url])
    if not urls:
        warn(no_urls_found_message())
        return 2
    say("Ein Browserfenster öffnet sich: einloggen und das Fenster danach schließen.")
    try:
        count = interactive_login(urls[0], login_profile_dir(), log=lambda _text: None)
    except BrowserLoginError as exc:
        warn(f"Fehler: {exc}")
        return 1
    if count:
        say(f"Login für {site_of(urls[0])} gespeichert.")
        return 0
    warn("Es wurde kein Login gespeichert. Warst du eingeloggt?")
    return 1


def logout_command(args: argparse.Namespace) -> int:
    if args.site:
        site = site_of(args.site)
        removed_credentials = delete_credentials(login_profile_dir(), args.site)
        if delete_site_login(login_profile_dir(), args.site) or removed_credentials:
            say(f"Login für {site} gelöscht.")
        else:
            say(f"Für {site} war kein Login gespeichert.")
        return 0
    delete_credentials(login_profile_dir())
    say("Alle Logins gelöscht." if delete_saved_login(login_profile_dir()) else "Es war kein Login gespeichert.")
    return 0


def settings_command(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.folder or args.quality:
        if args.folder:
            folder = Path(args.folder).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            settings["download_dir"] = str(folder)
        if args.quality:
            settings["quality"] = args.quality
        save_settings(settings)
    say(f"Ordner:    {settings['download_dir']}")
    say(f"Qualität:  {QUALITY_OPTIONS[settings['quality']][0]} ({settings['quality']})")
    if not (args.folder or args.quality):
        say("")
        say('Ändern mit: vd settings --folder "PFAD"   oder   vd settings -q 720p')
    return 0


def history_command(args: argparse.Namespace) -> int:
    if args.clear:
        clear_history()
        say("Verlauf gelöscht.")
        return 0
    entries = load_history()
    if not entries:
        say("Noch keine Downloads.")
        return 0
    for entry in reversed(entries[:20]):
        say(f"{format_history_timestamp(entry['downloaded_at'])}  {entry['title']}")
        say(f"                  {entry['url']}")
    return 0


def is_installed_app() -> bool:
    """True for the Windows app installed with mp4-downloader-setup.exe."""
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value)[:3])


def latest_release_version() -> str | None:
    request = urllib.request.Request(LATEST_RELEASE_API, headers={"User-Agent": f"vd/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            tag = json.load(response).get("tag_name", "")
    except Exception:  # noqa: BLE001 - offline or rate limited: just try the update
        return None
    return tag.lstrip("v") or None


def update_installed_app() -> int:
    latest = latest_release_version()
    if latest and version_tuple(latest) <= version_tuple(__version__):
        say(f"Du hast bereits die neueste Version ({__version__}).")
        return 0
    say(f"Lade Version {latest or 'neueste'}...")
    setup_path = Path(tempfile.gettempdir()) / "mp4-downloader-setup.exe"
    try:
        request = urllib.request.Request(SETUP_URL, headers={"User-Agent": f"vd/{__version__}"})
        with urllib.request.urlopen(request, timeout=60) as response, setup_path.open("wb") as file:
            shutil.copyfileobj(response, file)
    except Exception as exc:  # noqa: BLE001 - user-facing
        warn(f"Download des Updates fehlgeschlagen: {exc}")
        return 1
    # The installer replaces this program, so it runs on its own after vd has exited.
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [str(setup_path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=flags,
        close_fds=True,
    )
    say("Das Update wird im Hintergrund installiert. In etwa einer Minute ist die neue Version bereit.")
    return 0


def update_command(_args: argparse.Namespace) -> int:
    if is_installed_app():
        return update_installed_app()
    say("Aktualisiere vd und yt-dlp...")
    command = [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", REPO_ZIP_URL, "yt-dlp"]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        warn("Update fehlgeschlagen. Versuche es mit:")
        warn(f'  python -m pip install --upgrade "{REPO_ZIP_URL}" yt-dlp')
        return 1
    say("Fertig. Neue Version ist ab dem nächsten Aufruf aktiv.")
    return 0


def selftest_command(_args: argparse.Namespace) -> int:
    """Hidden check used by the release build: are all parts bundled and working?"""
    say(f"vd {__version__}")
    say(f"yt-dlp {yt_dlp.version.__version__ if yt_dlp else 'FEHLT'}")
    say(f"ffmpeg {'gefunden' if shutil.which('ffmpeg') else 'nicht gefunden'}")
    if yt_dlp is None:
        return 1
    try:
        from playwright.sync_api import sync_playwright

        from browsers import launch_headless

        with sync_playwright() as playwright:
            browser, choice = launch_headless(playwright)
            say(f"Browser: {choice.name}")
            page = browser.new_page()
            page.set_content("<title>vd-selftest</title>")
            title = page.title()
            browser.close()
    except Exception as exc:  # noqa: BLE001 - report everything
        warn(f"Hintergrund-Browser: FEHLER {exc}")
        return 1
    say(f"Hintergrund-Browser: ok ({title})")
    if os.name == "nt":
        from site_auth import _dpapi

        secret = "Pässwort-Test".encode("utf-8")
        if _dpapi(_dpapi(secret, protect=True), protect=False) != secret:
            warn("Verschlüsselung der Zugangsdaten: FEHLER")
            return 1
        say("Verschlüsselung der Zugangsdaten: ok")
    return 0


# --------------------------------------------------------------------------- argument parsing

HELP_EPILOG = """\
Befehle:
  vd login [LINK]        Einloggen (ohne LINK: gespeicherte Logins anzeigen)
  vd logout [SEITE]      Login löschen (ohne SEITE: alle)
  vd settings            Standard-Ordner und -Qualität anzeigen/ändern
  vd history             Letzte Downloads anzeigen
  vd update              vd und yt-dlp aktualisieren

Beispiele:
  vd "https://www.youtube.com/watch?v=..."
  vd -a "LINK"           nur Ton als MP3
  vd -q 720p "LINK1" "LINK2"
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vd",
        description="Videos per Link als MP4 (oder MP3) herunterladen.",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser._positionals.title = "Links"
    parser._optionals.title = "Optionen"
    parser.add_argument("urls", nargs="*", metavar="LINK", help="Ein oder mehrere Links")
    parser.add_argument("-q", "--quality", choices=list(QUALITY_OPTIONS), help="Qualität (Standard: 1080p, siehe vd settings)")
    parser.add_argument("-a", "--audio", action="store_true", help="Nur Ton als MP3")
    parser.add_argument("-f", "--folder", metavar="ORDNER", help="Zielordner für diesen Download")
    parser.add_argument("--playlist", action="store_true", help="Ganze Playlist statt nur ein Video laden")
    parser.add_argument("-h", "--help", action="help", help="Diese Hilfe anzeigen")
    parser.add_argument("--version", action="version", version=f"vd {__version__}", help="Version anzeigen")
    advanced = parser.add_argument_group("Erweitert")
    advanced.add_argument("--cookies", metavar="DATEI", help="Login-Cookies aus einer cookies.txt-Datei")
    advanced.add_argument("--referer", metavar="URL", help="Seite, auf der ein direkt kopierter Stream-Link eingebettet ist")
    advanced.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    return parser


def build_command_parsers() -> dict[str, argparse.ArgumentParser]:
    login = argparse.ArgumentParser(prog="vd login", description="Auf einer Webseite einloggen.")
    login.add_argument("url", nargs="?", metavar="LINK")
    logout = argparse.ArgumentParser(prog="vd logout", description="Gespeicherte Logins löschen.")
    logout.add_argument("site", nargs="?", metavar="SEITE", help="z. B. example.com (ohne: alle)")
    settings = argparse.ArgumentParser(prog="vd settings", description="Standard-Ordner und -Qualität.")
    settings.add_argument("-f", "--folder", metavar="ORDNER")
    settings.add_argument("-q", "--quality", choices=list(QUALITY_OPTIONS))
    history = argparse.ArgumentParser(prog="vd history", description="Letzte Downloads.")
    history.add_argument("--clear", action="store_true", help="Verlauf löschen")
    update = argparse.ArgumentParser(prog="vd update", description="vd und yt-dlp aktualisieren.")
    selftest = argparse.ArgumentParser(prog="vd selftest")
    return {
        "login": login, "logout": logout, "settings": settings, "history": history, "update": update,
        "selftest": selftest,
    }


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "login": login_command,
    "logout": logout_command,
    "settings": settings_command,
    "history": history_command,
    "update": update_command,
    "selftest": selftest_command,
}


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in COMMANDS:
        command = argv[0]
        return COMMANDS[command](build_command_parsers()[command].parse_args(argv[1:]))

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.urls:
        parser.print_help()
        return 2
    try:
        return download_command(args)
    except KeyboardInterrupt:
        warn("\nAbgebrochen.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
