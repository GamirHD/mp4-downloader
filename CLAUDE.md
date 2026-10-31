# Hinweise für Claude

## Umgebung des Besitzers (GamirHD)
- Windows-Rechner, Kommandozeile ist **PowerShell** (Befehle immer für PowerShell angeben, z. B. `Stop-Process -Name brave -Force` statt `taskkill`; `taskkill` ist dort nicht im PATH).
- Browser: **Brave**. `--cookies-from-browser brave` schlägt unter Windows fehl ("Failed to decrypt with DPAPI", App-Bound Encryption). Für Seiten mit Login: einmal `vd login LINK` (eigenes Browserfenster des Programms), danach reicht `vd "LINK"`. Alternativen: `--cookies-from-clipboard` oder `--cookies cookies.txt`.
- Die CLI `vd` ist per `python -m pip install` in die System-Python-Installation installiert (siehe `install.ps1`); zusätzliche Pakete wie Playwright mit `python -m pip install ...` installieren.
- Antworten auf Deutsch.

## Projekt
- Tests: `python -m unittest` (aus dem Repo-Ordner).
- Releases entstehen automatisch, wenn eine neue `version` in `pyproject.toml` (und `__version__` in `vd_cli.py`) auf `main` landet. Optionale Release-Notes: `.github/release-notes/vX.Y.Z.md`. Claude darf keine Releases/Tags direkt anlegen, nur Branches pushen und PRs mergen.
