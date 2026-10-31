"""Remember website logins in the app's own browser profile.

``vd login URL`` opens a browser window (the default browser when it is
Chromium-based, e.g. Brave) with a separate profile that belongs to this app. The user logs in once and closes the window; later downloads use the
saved cookies for that website automatically. The cookies are taken from the
browser while the window is open, so the Windows cookie encryption of
Chrome/Brave/Edge is not a problem. They are stored only in the app's settings
folder and handed to yt-dlp through a temporary file that is deleted afterwards.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from browsers import LAUNCH_ARGS, browser_choices, no_browser_message
from typing import Any, Callable, Iterator

CHANNEL_FILE = "vd-browser.txt"
COOKIES_FILE = "vd-cookies.json"


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


def _load_cookies(profile_dir: Path) -> list[dict[str, Any]]:
    path = profile_dir / COOKIES_FILE
    if not path.is_file():
        return []
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(cookies, list):
        return []
    return [cookie for cookie in cookies if isinstance(cookie, dict)]


def _cookie_key(cookie: dict[str, Any]) -> tuple[str, str, str]:
    return (str(cookie.get("name")), str(cookie.get("domain")).lower(), str(cookie.get("path") or "/"))


def _save_cookies(profile_dir: Path, cookies: list[dict[str, Any]], *, merge: bool = True) -> None:
    """Store cookies; logins of other websites stay untouched when merging."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    if merge:
        new_keys = {_cookie_key(cookie) for cookie in cookies}
        cookies = [c for c in _load_cookies(profile_dir) if _cookie_key(c) not in new_keys] + list(cookies)
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


def _reset_profile(profile_dir: Path) -> None:
    """Start a fresh browser profile but keep the saved logins (vd-cookies.json)."""
    for item in profile_dir.iterdir():
        if item.name == COOKIES_FILE:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def _launch(playwright: Any, profile_dir: Path, *, headless: bool) -> Any:
    """Open the login profile in the preferred browser (normally the default browser)."""
    candidates = browser_choices()
    saved_channel_file = profile_dir / CHANNEL_FILE
    saved_key = saved_channel_file.read_text(encoding="utf-8").strip() if saved_channel_file.is_file() else ""
    if saved_key and saved_key != candidates[0].key and profile_dir.is_dir():
        # The profile was made by another browser (e.g. Edge before Brave became the
        # default). Browser profiles are not interchangeable, so start a new one.
        _reset_profile(profile_dir)

    errors: list[str] = []
    for choice in candidates:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=headless,
                no_viewport=not headless,
                args=LAUNCH_ARGS,
                ignore_default_args=["--enable-automation"],
                **choice.launch_kwargs,
            )
        except Exception as exc:  # noqa: BLE001 - try the next browser
            errors.append(f"{choice.name}: {str(exc).splitlines()[0]}")
            continue
        profile_dir.mkdir(parents=True, exist_ok=True)
        saved_channel_file.write_text(choice.key, encoding="utf-8")
        return context
    raise BrowserLoginError(no_browser_message(errors))


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
    return [cookie for cookie in _load_cookies(profile_dir) if _cookie_matches(cookie, url)]


def site_of(value: str) -> str:
    """Normalize a link or domain to a site name like "example.com"."""
    text = value.strip().lower()
    host = urlparse(text).hostname if "://" in text else text.split("/", 1)[0]
    host = (host or "").lstrip(".")
    return host[4:] if host.startswith("www.") else host


def saved_sites(profile_dir: Path) -> list[tuple[str, int]]:
    """Websites with saved cookies and how many cookies each has."""
    counts: dict[str, int] = {}
    now = time.time()
    for cookie in _load_cookies(profile_dir):
        expires = cookie.get("expires")
        if isinstance(expires, (int, float)) and 0 < expires < now:
            continue
        site = site_of(str(cookie.get("domain") or ""))
        if site:
            counts[site] = counts.get(site, 0) + 1
    return sorted(counts.items())


def delete_site_login(profile_dir: Path, site: str) -> int:
    """Remove the saved cookies of one website. Returns how many were removed."""
    target = site_of(site)
    if not target:
        return 0
    cookies = _load_cookies(profile_dir)

    def belongs(cookie: dict[str, Any]) -> bool:
        domain = site_of(str(cookie.get("domain") or ""))
        return domain == target or domain.endswith(f".{target}")

    remaining = [cookie for cookie in cookies if not belongs(cookie)]
    removed = len(cookies) - len(remaining)
    if removed:
        _save_cookies(profile_dir, remaining, merge=False)
    return removed


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


@contextmanager
def temporary_cookie_file(content: str) -> Iterator[Path]:
    """Write cookies to a private temp file and always delete it afterwards."""
    handle, name = tempfile.mkstemp(prefix="vd-cookies-", suffix=".txt")
    path = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(content)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        yield path
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
