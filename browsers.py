"""Pick the browser vd uses for login windows and for finding embedded videos.

The user's default browser is preferred when it is Chromium-based (Brave, Chrome,
Edge, Vivaldi, ...), because Playwright can drive those directly. Otherwise vd
falls back to the installed Edge or Chrome and finally to Playwright's own
Chromium. Firefox as default browser is skipped: Playwright can only control
its own patched Firefox build.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Executable name -> display name of Chromium-based browsers
CHROMIUM_BROWSERS = {
    "brave.exe": "Brave",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "vivaldi.exe": "Vivaldi",
    "chromium.exe": "Chromium",
    "thorium.exe": "Thorium",
    "chrome": "Chrome",
    "brave": "Brave",
    "brave-browser": "Brave",
    "brave-browser-stable": "Brave",
    "google-chrome": "Chrome",
    "google-chrome-stable": "Chrome",
    "chromium": "Chromium",
    "chromium-browser": "Chromium",
    "microsoft-edge": "Edge",
    "microsoft-edge-stable": "Edge",
    "vivaldi": "Vivaldi",
    "vivaldi-stable": "Vivaldi",
}
LAUNCH_ARGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
]


@dataclass(frozen=True)
class BrowserChoice:
    key: str  # remembered with a login profile: "exe:<path>" or a Playwright channel
    name: str
    launch_kwargs: dict[str, Any] = field(default_factory=dict)


def _first_token(command: str) -> str:
    command = command.strip()
    if command.startswith('"'):
        return command[1:].split('"', 1)[0]
    try:
        return shlex.split(command, posix=os.name != "nt")[0]
    except (ValueError, IndexError):
        return command.split(" ", 1)[0]


def _windows_default_browser() -> str | None:
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
        ) as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as key:
            command = winreg.QueryValueEx(key, "")[0]
    except OSError:
        return None
    return _first_token(os.path.expandvars(command)) or None


def _linux_default_browser() -> str | None:
    if not shutil.which("xdg-settings"):
        return None
    try:
        desktop = subprocess.run(
            ["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    name = desktop.removesuffix(".desktop").split(".")[-1].lower()
    for candidate in (name, f"{name}-stable", name.replace("_", "-")):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def default_browser_executable() -> str | None:
    if os.name == "nt":
        return _windows_default_browser()
    if sys.platform.startswith("linux"):
        return _linux_default_browser()
    return None


def chromium_name(executable: str | None) -> str | None:
    """Display name if ``executable`` is a Chromium-based browser, else None."""
    if not executable:
        return None
    return CHROMIUM_BROWSERS.get(Path(executable).name.lower())


def browser_choices(default_executable: str | None = None) -> list[BrowserChoice]:
    """Browsers to try, best first: default browser, Edge, Chrome, Playwright's Chromium."""
    if default_executable is None:
        default_executable = default_browser_executable()
    choices: list[BrowserChoice] = []
    name = chromium_name(default_executable)
    if name and default_executable and Path(default_executable).is_file():
        choices.append(BrowserChoice(f"exe:{default_executable}", name, {"executable_path": default_executable}))
    choices += [
        BrowserChoice("msedge", "Edge", {"channel": "msedge"}),
        BrowserChoice("chrome", "Chrome", {"channel": "chrome"}),
        BrowserChoice("chromium", "Chromium", {}),
    ]
    return choices


def choice_from_key(key: str) -> BrowserChoice | None:
    for choice in browser_choices():
        if choice.key == key:
            return choice
    if key.startswith("exe:") and Path(key[4:]).is_file():
        path = key[4:]
        return BrowserChoice(key, chromium_name(path) or "Browser", {"executable_path": path})
    return None


def launch_headless(playwright: Any) -> tuple[Any, BrowserChoice]:
    """Start a hidden browser for searching pages; returns (browser, choice)."""
    errors: list[str] = []
    for choice in browser_choices():
        try:
            browser = playwright.chromium.launch(
                headless=True,
                args=LAUNCH_ARGS,
                ignore_default_args=["--enable-automation"],
                **choice.launch_kwargs,
            )
        except Exception as exc:  # noqa: BLE001 - try the next browser
            errors.append(f"{choice.name}: {str(exc).splitlines()[0]}")
            continue
        return browser, choice
    raise RuntimeError(no_browser_message(errors))


def no_browser_message(errors: list[str]) -> str:
    return (
        "Es konnte kein Browser gestartet werden. Installiere Brave, Chrome oder Microsoft Edge. ("
        + "; ".join(errors)
        + ")"
    )
