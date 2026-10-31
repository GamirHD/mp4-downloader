"""Take over a login from the normal browser (e.g. Brave) via the clipboard.

Some websites allow only one active login at a time: logging in again in vd's own
browser window logs you out in your normal browser. Instead, the cookies of the
existing browser login are copied (browser extension "Get cookies.txt LOCALLY" ->
Copy) and imported, so both use the same session.

Accepted clipboard formats: Netscape cookies.txt text, or a ``Cookie`` request
header (``name=value; ...``) together with a link.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from browser_login import _load_cookies, _save_cookies, site_of


class CookieImportError(ValueError):
    pass


def _run_clipboard_command(args: list[str], input_text: str | None = None) -> str | None:
    if not shutil.which(args[0]):
        return None
    try:
        result = subprocess.run(
            args,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def read_clipboard_text() -> str:
    """Read text from the system clipboard without extra dependencies."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            return root.clipboard_get()
        finally:
            root.destroy()
    except Exception:  # noqa: BLE001 - fall back to platform tools
        pass

    if os.name == "nt":
        commands = [["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"]]
    elif sys.platform == "darwin":
        commands = [["pbpaste"]]
    else:
        commands = [["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "-b", "-o"]]
    for command in commands:
        text = _run_clipboard_command(command)
        if text is not None:
            return text
    raise CookieImportError("clipboard")


def clear_clipboard() -> bool:
    """Remove the login cookies from the clipboard again."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            root.clipboard_clear()
            root.clipboard_append("")
            root.update()
        finally:
            root.destroy()
        return True
    except Exception:  # noqa: BLE001 - fall back to platform tools
        pass
    if os.name == "nt":
        return _run_clipboard_command(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $null"]) is not None
    if sys.platform == "darwin":
        return _run_clipboard_command(["pbcopy"], input_text="") is not None
    for command in (["wl-copy", "--clear"], ["xclip", "-selection", "clipboard"], ["xsel", "-b", "-c"]):
        if _run_clipboard_command(command, input_text="") is not None:
            return True
    return False


def parse_cookies(text: str, url: str | None = None) -> list[dict[str, Any]]:
    """Cookies from cookies.txt text or a Cookie header, in the format of the saved logins."""
    cookies: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        http_only = line.startswith("#HttpOnly_")
        if http_only:
            line = line[len("#HttpOnly_"):]
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            continue
        domain, _subdomains, path, secure, expires, name, value = fields
        try:
            expires_at = float(expires)
        except ValueError:
            expires_at = 0
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path or "/",
            "expires": expires_at if expires_at > 0 else -1,
            "secure": secure.upper() == "TRUE",
            "httpOnly": http_only,
        })
    if cookies:
        return cookies

    header = (text or "").strip()
    if header.lower().startswith("cookie:"):
        header = header.split(":", 1)[1]
    host = (urlparse(url).hostname or "") if url else ""
    if not host or "=" not in header or "\n" in header.strip():
        return []
    domain = "." + (host[4:] if host.startswith("www.") else host)
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name.strip() and " " not in name.strip():
            cookies.append({"name": name.strip(), "value": value.strip(), "domain": domain, "path": "/",
                            "expires": -1, "secure": False, "httpOnly": False})
    return cookies


def import_cookies(profile_dir: Path, text: str, url: str | None = None) -> dict[str, int]:
    """Replace the saved login of each website in ``text``. Returns {site: number of cookies}."""
    cookies = parse_cookies(text, url)
    now = time.time()
    cookies = [c for c in cookies if not (isinstance(c["expires"], float) and 0 < c["expires"] < now)]
    if not cookies:
        raise CookieImportError("no cookies")
    sites: dict[str, int] = {}
    for cookie in cookies:
        site = site_of(cookie["domain"])
        sites[site] = sites.get(site, 0) + 1

    def belongs_to_imported_site(cookie: dict[str, Any]) -> bool:
        domain = site_of(str(cookie.get("domain") or ""))
        return any(domain == site or domain.endswith(f".{site}") for site in sites)

    # Old cookies of these websites (e.g. from vd's own login window) would belong to another session.
    kept = [c for c in _load_cookies(profile_dir) if not belongs_to_imported_site(c)]
    _save_cookies(profile_dir, kept + cookies, merge=False)
    return sites
