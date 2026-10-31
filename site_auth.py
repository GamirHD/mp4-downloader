"""HTTP login (Benutzername/Passwort-Abfrage des Browsers, "Basic Auth").

Some websites, e.g. many university servers, do not use a login page with
cookies but let the browser ask for user name and password. vd asks for them,
sends them only to that one website (yt-dlp: an Authorization header added to
each request for that website; hidden browser: an origin restriction) and
remembers them per website.

On Windows the password is stored encrypted for the current Windows user
(DPAPI). On other systems it is only kept for the running program.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

CREDENTIALS_FILE = "vd-credentials.json"
_session_credentials: dict[str, "Credentials"] = {}


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


def site_key(url: str) -> str:
    """Credentials belong to scheme + host (+ port), like the browser does it."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{(parts.hostname or '').lower()}" + (f":{parts.port}" if parts.port else "")


def is_http_auth_error(text: str) -> bool:
    lower = text.lower()
    return "http error 401" in lower or "err_invalid_auth_credentials" in lower or "401: unauthorized" in lower


def basic_auth_header(credentials: Credentials) -> str:
    token = base64.b64encode(f"{credentials.username}:{credentials.password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def playwright_http_credentials(url: str, credentials: Credentials | None) -> dict[str, str] | None:
    if credentials is None:
        return None
    return {"username": credentials.username, "password": credentials.password, "origin": site_key(url)}


# --------------------------------------------------------------------------- storage


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    data_in = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    data_out = DataBlob()
    crypt32 = ctypes.windll.crypt32
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = function(ctypes.byref(data_in), None, None, None, None, 0x1, ctypes.byref(data_out))  # UI_FORBIDDEN
    if not ok:
        raise OSError("Windows-Verschlüsselung (DPAPI) fehlgeschlagen")
    try:
        return ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(data_out.pbData)


def can_store_securely() -> bool:
    return os.name == "nt"


def _load(profile_dir: Path) -> dict[str, dict[str, str]]:
    try:
        data = json.loads((profile_dir / CREDENTIALS_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _store(profile_dir: Path, data: dict[str, dict[str, str]]) -> None:
    path = profile_dir / CREDENTIALS_FILE
    if not data:
        path.unlink(missing_ok=True)
        return
    profile_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_credentials(profile_dir: Path, url: str, credentials: Credentials) -> bool:
    """Remember credentials for the website of ``url``. Returns True if stored on disk."""
    key = site_key(url)
    _session_credentials[key] = credentials
    if not can_store_securely():
        return False
    data = _load(profile_dir)
    protected = _dpapi(credentials.password.encode("utf-8"), protect=True)
    data[key] = {"username": credentials.username, "password_dpapi": base64.b64encode(protected).decode()}
    _store(profile_dir, data)
    return True


def load_credentials(profile_dir: Path, url: str) -> Credentials | None:
    key = site_key(url)
    if key in _session_credentials:
        return _session_credentials[key]
    entry = _load(profile_dir).get(key)
    if not isinstance(entry, dict) or not can_store_securely():
        return None
    try:
        password = _dpapi(base64.b64decode(entry["password_dpapi"]), protect=False).decode("utf-8")
    except (KeyError, ValueError, OSError):
        return None
    credentials = Credentials(str(entry.get("username", "")), password)
    _session_credentials[key] = credentials
    return credentials


def delete_credentials(profile_dir: Path, site: str | None = None) -> int:
    """Forget credentials of one website (host name or link) or of all websites."""
    data = _load(profile_dir)
    if site is None:
        removed = len(data) + len(_session_credentials)
        _session_credentials.clear()
        _store(profile_dir, {})
        return removed
    host = (urlsplit(site).hostname if "://" in site else site.split("/", 1)[0]) or ""
    host = host.lower().removeprefix("www.")

    def matches(key: str) -> bool:
        key_host = (urlsplit(key).hostname or "").removeprefix("www.")
        return key_host == host or key_host.endswith(f".{host}")

    removed = 0
    for key in [k for k in data if matches(k)]:
        del data[key]
        removed += 1
    for key in [k for k in _session_credentials if matches(k)]:
        del _session_credentials[key]
        removed += 1
    _store(profile_dir, data)
    return removed


def credential_sites(profile_dir: Path) -> list[str]:
    hosts = {(urlsplit(key).hostname or "").removeprefix("www.") for key in _load(profile_dir)}
    return sorted(host for host in hosts if host)
