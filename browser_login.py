"""Remember website logins in the app's own browser profile.

``vd login URL`` opens a normal browser window with a profile that belongs to
this app. The user logs in once and closes the window. Later downloads read the
cookies for the link from that profile automatically, so no cookies file or
clipboard step is needed. The cookies are taken from the browser while the
window is open, so the Windows cookie encryption of Chrome/Brave/Edge is not
a problem. They are stored only in the app's settings folder.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Callable

CHANNEL_FILE = "vd-browser.txt"
COOKIES_FILE = "vd-cookies.json"
BROWSER_CHANNELS = ("msedge", "chrome", "chromium")


class BrowserLoginError(RuntimeError):
    pass


def _sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserLoginError(
            "Fuer den gespeicherten Login wird Playwright gebraucht: `python -m pip install playwright`."
        ) from exc
    return sync_playwright


def has_saved_login(profile_dir: Path) -> bool:
    return (profile_dir / COOKIES_FILE).is_file()


def _save_cookies(profile_dir: Path, cookies: list[dict[str, Any]]) -> None:
    path = profile_dir / COOKIES_FILE
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(cookies), encoding="utf-8")
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass
    temp_path.replace(path)


def _cookie_matches(cookie: dict[str, Any], url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    domain = str(cookie.get("domain") or "").lower()
    bare = domain.lstrip(".")
    if not bare or not (host == bare or host.endswith(f".{bare}")):
        return False
    if not domain.startswith(".") and host != bare:
        return False
    path = str(cookie.get("path") or "/")
    if not (parsed.path or "/").startswith(path.rstrip("/") or "/"):
        return False
    expires = cookie.get("expires")
    if isinstance(expires, (int, float)) and expires > 0 and expires < time.time():
        return False
    return True


def _launch(playwright: Any, profile_dir: Path, *, headless: bool) -> Any:
    saved_channel_file = profile_dir / CHANNEL_FILE
    channels: tuple[str, ...] = BROWSER_CHANNELS
    if saved_channel_file.is_file():
        # The profile must always be opened with the browser that created it.
        channels = (saved_channel_file.read_text(encoding="utf-8").strip() or "chromium",)

    errors: list[str] = []
    for channel in channels:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel=None if channel == "chromium" else channel,
                headless=headless,
                no_viewport=not headless,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
        except Exception as exc:  # noqa: BLE001 - try the next browser
            errors.append(f"{channel}: {str(exc).splitlines()[0]}")
            continue
        profile_dir.mkdir(parents=True, exist_ok=True)
        saved_channel_file.write_text(channel, encoding="utf-8")
        return context
    raise BrowserLoginError(
        "Es konnte kein Browser gestartet werden. Installiere Microsoft Edge oder Chrome "
        "oder fuehre `python -m playwright install chromium` aus. (" + "; ".join(errors) + ")"
    )


def interactive_login(url: str, profile_dir: Path, *, log: Callable[[str], None] = print) -> int:
    """Open a visible window for logging in. Returns the number of saved cookies for ``url``."""
    sync_playwright = _sync_playwright()
    profile_dir.mkdir(parents=True, exist_ok=True)
    snapshot: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        context = _launch(playwright, profile_dir, headless=False)
        closed: list[bool] = []
        context.on("close", lambda _context: closed.append(True))
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        log("Ein Browserfenster ist offen: logge dich dort ein und schliesse danach das Fenster.")
        # Keep a copy of the cookies while the window is open, so nothing depends
        # on how the browser is closed.
        while not closed:
            try:
                snapshot = list(context.cookies()) or snapshot
            except Exception:  # noqa: BLE001 - window was closed
                break
            time.sleep(1)
        try:
            context.close()
        except Exception:  # noqa: BLE001 - already closed
            pass
    _save_cookies(profile_dir, snapshot)
    return len(saved_cookies_for(url, profile_dir))


def saved_cookies_for(url: str, profile_dir: Path) -> list[dict[str, Any]]:
    """Return the saved cookies that would be sent to ``url``."""
    path = profile_dir / COOKIES_FILE
    if not path.is_file():
        return []
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(cookies, list):
        return []
    return [cookie for cookie in cookies if isinstance(cookie, dict) and _cookie_matches(cookie, url)]


def cookies_to_netscape(cookies: list[dict[str, Any]]) -> str:
    lines = ["# Netscape HTTP Cookie File"]
    for cookie in cookies:
        domain = str(cookie.get("domain") or "")
        if not domain or "\t" in str(cookie.get("value", "")):
            continue
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        expires = cookie.get("expires")
        expires_text = str(int(expires)) if isinstance(expires, (int, float)) and expires > 0 else "0"
        prefix = "#HttpOnly_" if cookie.get("httpOnly") else ""
        lines.append(
            "\t".join(
                [
                    f"{prefix}{domain}",
                    include_subdomains,
                    str(cookie.get("path") or "/"),
                    "TRUE" if cookie.get("secure") else "FALSE",
                    expires_text,
                    str(cookie.get("name") or ""),
                    str(cookie.get("value") or ""),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def delete_saved_login(profile_dir: Path) -> bool:
    if not profile_dir.exists():
        return False
    shutil.rmtree(profile_dir, ignore_errors=True)
    return not profile_dir.exists()
