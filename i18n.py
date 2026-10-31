"""Texts shown to the user, in English (default) and German.

Usage: ``t("saved", path=...)``. The language comes from the settings
(``vd settings --language de``) and can be overridden with the environment
variable ``VD_LANG``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

LANGUAGES = {"en": "English", "de": "Deutsch"}
DEFAULT_LANGUAGE = "en"
_current: str | None = None

MESSAGES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ qualities
    "quality.best": {"en": "Best quality", "de": "Beste Qualität"},
    "quality.original": {"en": "Original file (largest)", "de": "Originaldatei (größte)"},
    "quality.1080p": {"en": "Up to 1080p", "de": "Bis 1080p"},
    "quality.720p": {"en": "Up to 720p", "de": "Bis 720p"},
    "quality.480p": {"en": "Up to 480p", "de": "Bis 480p"},
    "quality.mp3": {"en": "Audio only (MP3)", "de": "Nur Ton (MP3)"},
    # ------------------------------------------------------------------ downloading
    "downloading": {"en": "Downloading: {name}", "de": "Lade: {name}"},
    "audio_part": {"en": " (audio)", "de": " (Ton)"},
    "progress_of": {"en": "{done} of {total}", "de": "{done} von {total}"},
    "progress_left": {"en": "{eta} left", "de": "noch {eta}"},
    "saved": {"en": "Saved: {path}", "de": "Gespeichert: {path}"},
    "searching_page": {"en": "Looking for the video on the page...", "de": "Suche das Video auf der Seite..."},
    "error": {"en": "Error: {message}", "de": "Fehler: {message}"},
    "cancelled": {"en": "Cancelled.", "de": "Abgebrochen."},
    "failures": {"en": "{failed} of {total} downloads failed.", "de": "{failed} von {total} Downloads fehlgeschlagen."},
    "no_links": {
        "en": "No link found. Please enter an address like https://...",
        "de": "Kein Link erkannt. Bitte eine Adresse wie https://... angeben.",
    },
    "no_embedded_video": {
        "en": 'No embedded video found on the page. If the page needs a login: vd login "{url}"',
        "de": 'Kein eingebettetes Video auf der Seite gefunden. Falls die Seite einen Login braucht: vd login "{url}"',
    },
    "login_page_shown": {
        "en": "The page shows a login page instead of the video.",
        "de": "Die Seite zeigt eine Login-Seite statt des Videos.",
    },
    "ytdlp_missing": {"en": "yt-dlp is missing. Please reinstall vd.", "de": "yt-dlp fehlt. Installiere vd neu."},
    "playwright_missing": {
        "en": "Playwright is missing (needed for pages with their own video player). Fix: vd update",
        "de": "Playwright fehlt (für Seiten mit eigenem Video-Player). Behebung: vd update",
    },
    "browser_search_failed": {
        "en": "The video search in the background browser failed: {error}",
        "de": "Die Video-Suche im Hintergrund-Browser ist fehlgeschlagen: {error}",
    },
    # ------------------------------------------------------------------ friendly errors
    "err.drm": {
        "en": "This video is copy-protected (DRM) and cannot be downloaded "
        "(e.g. Netflix, Disney+, Prime Video) - not even with a login.",
        "de": "Dieses Video ist kopiergeschützt (DRM) und kann nicht heruntergeladen werden "
        "(z. B. Netflix, Disney+, Prime Video) - auch nicht mit Login.",
    },
    "err.ffmpeg": {
        "en": "ffmpeg is missing. Install it (Windows: winget install Gyan.FFmpeg) and open a new terminal.",
        "de": "ffmpeg fehlt. Installiere es (Windows: winget install Gyan.FFmpeg) und öffne ein neues Terminal.",
    },
    "err.http_auth": {
        "en": "User name or password is missing or wrong (HTTP 401).",
        "de": "Benutzername oder Passwort fehlt oder ist falsch (HTTP 401).",
    },
    "err.youtube_login": {
        "en": "YouTube requires a login. Log in with `vd login https://www.youtube.com`.",
        "de": "YouTube verlangt einen Login. Logge dich mit `vd login https://www.youtube.com` ein.",
    },
    "err.unsupported": {"en": "This link is not supported.", "de": "Dieser Link wird nicht unterstützt."},
    "err.404": {
        "en": "The page was not found (404). Please check the link.",
        "de": "Die Seite wurde nicht gefunden (404). Bitte den Link prüfen.",
    },
    # ------------------------------------------------------------------ login
    "login_tip": {"en": 'Tip: vd login "{url}"', "de": 'Tipp: vd login "{url}"'},
    "ask_login_expired": {
        "en": "The login for {site} may have expired. Log in again?",
        "de": "Der Login für {site} ist vielleicht abgelaufen. Neu einloggen?",
    },
    "ask_login_needed": {
        "en": "{site} probably needs a login. Log in now?",
        "de": "{site} braucht vermutlich einen Login. Jetzt einloggen?",
    },
    "login_window": {
        "en": "A browser window opens: log in, then close the window.",
        "de": "Ein Browserfenster öffnet sich: einloggen und das Fenster danach schließen.",
    },
    "login_none_saved": {"en": "No login was saved.", "de": "Es wurde kein Login gespeichert."},
    "login_none_saved_hint": {
        "en": "No login was saved. Were you logged in?",
        "de": "Es wurde kein Login gespeichert. Warst du eingeloggt?",
    },
    "login_saved_retry": {
        "en": "Login for {site} saved. Trying again...",
        "de": "Login für {site} gespeichert. Neuer Versuch...",
    },
    "login_saved": {"en": "Login for {site} saved.", "de": "Login für {site} gespeichert."},
    "logins_none": {
        "en": 'No logins saved yet. Log in with: vd login "LINK"',
        "de": 'Noch keine Logins gespeichert. Einloggen mit: vd login "LINK"',
    },
    "logins_title": {"en": "Saved logins:", "de": "Gespeicherte Logins:"},
    "logins_logout_hint": {"en": "Log out with: vd logout SITE", "de": "Ausloggen mit: vd logout SEITE"},
    "logout_done": {"en": "Login for {site} deleted.", "de": "Login für {site} gelöscht."},
    "logout_none": {"en": "There was no login saved for {site}.", "de": "Für {site} war kein Login gespeichert."},
    "logout_all": {"en": "All logins deleted.", "de": "Alle Logins gelöscht."},
    "logout_nothing": {"en": "No login was saved.", "de": "Es war kein Login gespeichert."},
    "import_done": {
        "en": "Login for {site} taken over from your browser ({count} cookies). Clipboard cleared.",
        "de": "Login für {site} aus dem Browser übernommen ({count} Cookies). Zwischenablage geleert.",
    },
    "import_none": {
        "en": "No login found in the clipboard.\nIn your browser: open the website (logged in), click the extension "
        "\"Get cookies.txt LOCALLY\" -> Copy. Then run this again.",
        "de": "Kein Login in der Zwischenablage gefunden.\nIm Browser: Webseite öffnen (eingeloggt), Erweiterung "
        "\"Get cookies.txt LOCALLY\" anklicken -> Copy. Danach erneut ausführen.",
    },
    "import_clipboard_error": {
        "en": "The clipboard could not be read.",
        "de": "Die Zwischenablage konnte nicht gelesen werden.",
    },
    "help.login_import": {
        "en": "Take over the login of your normal browser from the clipboard (for sites that allow only one login)",
        "de": "Login deines normalen Browsers aus der Zwischenablage übernehmen (für Seiten, die nur einen Login erlauben)",
    },
    "gui.import": {"en": "Take over from browser...", "de": "Aus Browser übernehmen..."},
    "gui.import_help": {
        "en": "For websites that allow only one login at a time (otherwise you are logged out in your browser):\n\n"
        "1. Open the website in your browser and make sure you are logged in.\n"
        "2. Click the browser extension \"Get cookies.txt LOCALLY\" -> Copy.\n"
        "3. Click OK.",
        "de": "Für Webseiten, die nur einen Login gleichzeitig erlauben (sonst wirst du im Browser ausgeloggt):\n\n"
        "1. Webseite im Browser öffnen, eingeloggt sein.\n"
        "2. Browser-Erweiterung \"Get cookies.txt LOCALLY\" anklicken -> Copy.\n"
        "3. Auf OK klicken.",
    },
    "no_browser": {
        "en": "Could not start a browser. Please install Brave, Chrome or Microsoft Edge. ({errors})",
        "de": "Es konnte kein Browser gestartet werden. Installiere Brave, Chrome oder Microsoft Edge. ({errors})",
    },
    # ------------------------------------------------------------------ HTTP login (user name/password)
    "credentials_required": {
        "en": "{site} asks for a user name and password.",
        "de": "{site} verlangt Benutzername und Passwort.",
    },
    "credentials_need_terminal": {
        "en": "{site} asks for a user name and password. Run vd in a terminal to enter them.",
        "de": "{site} verlangt Benutzername und Passwort. Starte vd im Terminal, um sie einzugeben.",
    },
    "credentials_cancelled": {
        "en": "Cancelled: no user name and password entered.",
        "de": "Abgebrochen: keine Zugangsdaten eingegeben.",
    },
    "credentials_saved": {
        "en": "User name and password for {site} saved (encrypted).",
        "de": "Zugangsdaten für {site} gespeichert (verschlüsselt).",
    },
    "credentials_wrong": {"en": "Wrong user name or password.", "de": "Benutzername oder Passwort falsch."},
    "prompt_username": {"en": "User name: ", "de": "Benutzername: "},
    "prompt_password": {"en": "Password (hidden): ", "de": "Passwort (wird nicht angezeigt): "},
    "dpapi_failed": {"en": "Windows encryption (DPAPI) failed", "de": "Windows-Verschlüsselung (DPAPI) fehlgeschlagen"},
    "yes_no_default_yes": {"en": " [Y/n] ", "de": " [J/n] "},
    "yes_no_default_no": {"en": " [y/N] ", "de": " [j/N] "},
    # ------------------------------------------------------------------ settings / history / update
    "settings_folder": {"en": "Folder:    {value}", "de": "Ordner:    {value}"},
    "settings_quality": {"en": "Quality:   {value}", "de": "Qualität:  {value}"},
    "settings_language": {"en": "Language:  {value}", "de": "Sprache:   {value}"},
    "settings_hint": {
        "en": 'Change with: vd settings --folder "PATH"  |  -q 720p  |  --language de',
        "de": 'Ändern mit: vd settings --folder "PFAD"  |  -q 720p  |  --language en',
    },
    "history_cleared": {"en": "History cleared.", "de": "Verlauf gelöscht."},
    "history_empty": {"en": "No downloads yet.", "de": "Noch keine Downloads."},
    "update_latest": {
        "en": "You already have the latest version ({version}).",
        "de": "Du hast bereits die neueste Version ({version}).",
    },
    "update_downloading": {"en": "Downloading version {version}...", "de": "Lade Version {version}..."},
    "update_newest": {"en": "newest", "de": "neueste"},
    "update_download_failed": {
        "en": "Downloading the update failed: {error}",
        "de": "Download des Updates fehlgeschlagen: {error}",
    },
    "update_installing": {
        "en": "The update is being installed in the background. The new version is ready in about a minute.",
        "de": "Das Update wird im Hintergrund installiert. In etwa einer Minute ist die neue Version bereit.",
    },
    "update_pip": {"en": "Updating vd and yt-dlp...", "de": "Aktualisiere vd und yt-dlp..."},
    "update_failed": {"en": "Update failed. Try:", "de": "Update fehlgeschlagen. Versuche es mit:"},
    "update_done": {
        "en": "Done. The new version is active from the next start.",
        "de": "Fertig. Neue Version ist ab dem nächsten Aufruf aktiv.",
    },
    # ------------------------------------------------------------------ command line help
    "help.description": {
        "en": "Download videos from a link as MP4 (or MP3).",
        "de": "Videos per Link als MP4 (oder MP3) herunterladen.",
    },
    "help.links_title": {"en": "Links", "de": "Links"},
    "help.options_title": {"en": "Options", "de": "Optionen"},
    "help.advanced_title": {"en": "Advanced", "de": "Erweitert"},
    "help.links": {"en": "One or more links", "de": "Ein oder mehrere Links"},
    "help.quality": {
        "en": "Quality (default: 1080p, see vd settings)",
        "de": "Qualität (Standard: 1080p, siehe vd settings)",
    },
    "help.audio": {"en": "Audio only as MP3", "de": "Nur Ton als MP3"},
    "help.folder": {"en": "Target folder for this download", "de": "Zielordner für diesen Download"},
    "help.playlist": {"en": "Download a whole playlist instead of one video", "de": "Ganze Playlist statt nur ein Video laden"},
    "help.help": {"en": "Show this help", "de": "Diese Hilfe anzeigen"},
    "help.version": {"en": "Show the version", "de": "Version anzeigen"},
    "help.cookies": {"en": "Login cookies from a cookies.txt file", "de": "Login-Cookies aus einer cookies.txt-Datei"},
    "help.referer": {
        "en": "Page in which a directly copied stream link is embedded",
        "de": "Seite, auf der ein direkt kopierter Stream-Link eingebettet ist",
    },
    "help.metavar_folder": {"en": "FOLDER", "de": "ORDNER"},
    "help.metavar_file": {"en": "FILE", "de": "DATEI"},
    "help.metavar_site": {"en": "SITE", "de": "SEITE"},
    "help.epilog": {
        "en": """\
Commands:
  vd login [LINK]        Log in (without LINK: show saved logins)
  vd login --import      Take over the login of your browser (clipboard)
  vd logout [SITE]       Delete a login (without SITE: all)
  vd settings            Show/change default folder, quality and language
  vd history             Show recent downloads
  vd update              Update vd and yt-dlp

Examples:
  vd "https://www.youtube.com/watch?v=..."
  vd -a "LINK"           audio only as MP3
  vd -q 720p "LINK1" "LINK2"
""",
        "de": """\
Befehle:
  vd login [LINK]        Einloggen (ohne LINK: gespeicherte Logins anzeigen)
  vd login --import      Login deines Browsers übernehmen (Zwischenablage)
  vd logout [SEITE]      Login löschen (ohne SEITE: alle)
  vd settings            Standard-Ordner, -Qualität und Sprache anzeigen/ändern
  vd history             Letzte Downloads anzeigen
  vd update              vd und yt-dlp aktualisieren

Beispiele:
  vd "https://www.youtube.com/watch?v=..."
  vd -a "LINK"           nur Ton als MP3
  vd -q 720p "LINK1" "LINK2"
""",
    },
    "help.cmd_login": {"en": "Log in on a website.", "de": "Auf einer Webseite einloggen."},
    "help.cmd_logout": {"en": "Delete saved logins.", "de": "Gespeicherte Logins löschen."},
    "help.cmd_logout_site": {"en": "e.g. example.com (without: all)", "de": "z. B. example.com (ohne: alle)"},
    "help.cmd_settings": {
        "en": "Default folder, quality and language.",
        "de": "Standard-Ordner, -Qualität und Sprache.",
    },
    "help.cmd_language": {"en": "Language: en (English) or de (Deutsch)", "de": "Sprache: en (English) oder de (Deutsch)"},
    "help.cmd_history": {"en": "Recent downloads.", "de": "Letzte Downloads."},
    "help.cmd_history_clear": {"en": "Clear the history", "de": "Verlauf löschen"},
    "help.cmd_update": {"en": "Update vd and yt-dlp.", "de": "vd und yt-dlp aktualisieren."},
    # ------------------------------------------------------------------ GUI
    "gui.title": {"en": "Video Downloader", "de": "Video-Downloader"},
    "gui.links": {"en": "Links (one per line)", "de": "Links (einer pro Zeile)"},
    "gui.paste": {"en": "Paste", "de": "Einfügen"},
    "gui.clear": {"en": "Clear", "de": "Leeren"},
    "gui.quality": {"en": "Quality", "de": "Qualität"},
    "gui.folder": {"en": "Folder", "de": "Ordner"},
    "gui.choose": {"en": "Choose...", "de": "Wählen..."},
    "gui.open": {"en": "Open", "de": "Öffnen"},
    "gui.playlist": {"en": "Whole playlist", "de": "Ganze Playlist"},
    "gui.download": {"en": "Download", "de": "Herunterladen"},
    "gui.activity": {"en": "Activity", "de": "Protokoll"},
    "gui.cancel": {"en": "Cancel", "de": "Abbrechen"},
    "gui.ready": {"en": "Ready", "de": "Bereit"},
    "gui.running": {"en": "Downloading...", "de": "Lädt herunter..."},
    "gui.running_n": {"en": "Download {index} of {total}...", "de": "Download {index} von {total}..."},
    "gui.processing": {"en": "Processing file...", "de": "Verarbeite Datei..."},
    "gui.speed": {"en": "{percent} · {speed} · {eta} left", "de": "{percent} · {speed} · noch {eta}"},
    "gui.done": {"en": "Done", "de": "Fertig"},
    "gui.done_all": {"en": "All {total} downloads finished.", "de": "Alle {total} Downloads fertig."},
    "gui.done_one": {"en": "Download finished.", "de": "Download fertig."},
    "gui.done_errors": {"en": "Finished with errors", "de": "Fertig mit Fehlern"},
    "gui.cancelling": {"en": "Cancelling...", "de": "Wird abgebrochen..."},
    "gui.no_links": {"en": "Please paste at least one link.", "de": "Bitte mindestens einen Link einfügen."},
    "gui.folder_error": {"en": "The folder cannot be created:\n{error}", "de": "Der Ordner kann nicht erstellt werden:\n{error}"},
    "gui.open_error": {"en": "The folder cannot be opened:\n{error}", "de": "Der Ordner kann nicht geöffnet werden:\n{error}"},
    "gui.logins": {"en": "Logins...", "de": "Logins..."},
    "gui.logins_title": {"en": "Saved logins", "de": "Gespeicherte Logins"},
    "gui.logins_empty": {
        "en": "No logins saved yet.\nIf a page needs a login, you will be asked automatically.",
        "de": "Noch keine Logins gespeichert.\nBraucht eine Seite einen Login, wirst du automatisch gefragt.",
    },
    "gui.logout": {"en": "Log out", "de": "Ausloggen"},
    "gui.close": {"en": "Close", "de": "Schließen"},
    "gui.language": {"en": "Language", "de": "Sprache"},
    "gui.login_hint": {
        "en": "If a page needs a login, you will be asked and a browser window opens.",
        "de": "Braucht eine Seite einen Login, wirst du gefragt und ein Browserfenster öffnet sich.",
    },
    "gui.credentials_prompt": {
        "en": "{intro}{site} asks for a login.\n\nUser name:",
        "de": "{intro}{site} verlangt eine Anmeldung.\n\nBenutzername:",
    },
    "gui.credentials_wrong": {
        "en": "The user name or password was wrong.\n\n",
        "de": "Benutzername oder Passwort war falsch.\n\n",
    },
    "gui.password_for": {"en": "Password for {user}:", "de": "Passwort für {user}:"},
    "gui.login_window_status": {
        "en": "Browser window open: log in and close the window...",
        "de": "Browserfenster offen: einloggen und Fenster schließen...",
    },
}


def _settings_language() -> str | None:
    # Read the language without importing vd_cli (avoids an import cycle).
    if os.name == "nt" and os.environ.get("APPDATA"):
        path = Path(os.environ["APPDATA"]) / "mp4-downloader" / "settings.json"
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mp4-downloader" / "settings.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        return None
    return value if value in LANGUAGES else None


def get_language() -> str:
    global _current
    if _current is None:
        env = (os.environ.get("VD_LANG") or "").strip().lower()[:2]
        _current = env if env in LANGUAGES else (_settings_language() or DEFAULT_LANGUAGE)
    return _current


def set_language(language: str | None) -> None:
    """Switch the language for this program run (``None``: read it again from the settings)."""
    global _current
    _current = language if language in LANGUAGES else None


def t(key: str, **values: Any) -> str:
    entry = MESSAGES[key]
    text = entry.get(get_language()) or entry[DEFAULT_LANGUAGE]
    return text.format(**values) if values else text
