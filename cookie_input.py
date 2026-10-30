"""Use login cookies without leaving a cookies file behind.

Cookies can be pasted from the clipboard in two formats:

* Netscape ``cookies.txt`` text (e.g. "Copy" in the "Get cookies.txt LOCALLY"
  browser extension)
* a ``Cookie`` request header (``name=value; name2=value2``), e.g. copied from
  the browser developer tools

The cookies are written to a private temporary file only while downloading and
the file is deleted afterwards.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"


class CookieInputError(ValueError):
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
    raise CookieInputError("Die Zwischenablage konnte nicht gelesen werden.")


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


def _cookie_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise CookieInputError("Aus dem Link kann keine Domain fuer die Cookies bestimmt werden.")
    if host.startswith("www."):
        host = host[4:]
    return host


def _netscape_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        content = line[len("#HttpOnly_"):] if line.startswith("#HttpOnly_") else line
        if not content.strip() or content.startswith("#"):
            continue
        if len(content.split("\t")) == 7:
            lines.append(line)
    return lines


def cookies_text_to_netscape(text: str, url: str) -> tuple[str, int]:
    """Convert pasted cookies to Netscape format. Returns (file content, cookie count)."""
    stripped = (text or "").strip()
    if not stripped:
        raise CookieInputError("Die Zwischenablage ist leer. Bitte zuerst die Cookies kopieren.")

    lines = _netscape_lines(stripped)
    if lines:
        return NETSCAPE_HEADER + "\n".join(lines) + "\n", len(lines)

    header = stripped
    if header.lower().startswith("cookie:"):
        header = header.split(":", 1)[1]
    if "\n" in header.strip() or "=" not in header:
        raise CookieInputError(
            "In der Zwischenablage sind keine Cookies. Erwartet wird cookies.txt-Text "
            "oder ein Cookie-Header wie `name=wert; name2=wert2`."
        )

    domain = _cookie_domain(url)
    entries = []
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        name = name.strip()
        if not sep or not name or any(char in name for char in " \t"):
            continue
        entries.append(f".{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value.strip()}")
    if not entries:
        raise CookieInputError("Im kopierten Cookie-Header wurden keine Cookies erkannt.")
    return NETSCAPE_HEADER + "\n".join(entries) + "\n", len(entries)


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
