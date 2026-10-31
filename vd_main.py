"""Entry point for the bundled Windows command `vd.exe` (built with PyInstaller)."""

from vd_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
