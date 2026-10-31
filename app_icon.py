"""App icon (64x64 PNG) for windows and the Linux app menu, embedded so no data files are needed."""

from __future__ import annotations

import base64
from pathlib import Path

PNG_BASE64 = (
    "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"
)


def png_bytes() -> bytes:
    return base64.b64decode(PNG_BASE64)


def write_png(path: str | Path) -> None:
    """Used by install.sh to place the icon for the app menu."""
    Path(path).write_bytes(png_bytes())
