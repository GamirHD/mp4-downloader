# Hinweise für Claude

## Umgebung des Besitzers (GamirHD)
- Windows-Rechner, Kommandozeile ist **PowerShell** (Befehle immer für PowerShell angeben, z. B. `Stop-Process -Name brave -Force` statt `taskkill`; `taskkill` ist dort nicht im PATH).
- Browser: **Brave**. Cookies aus Chromium-Browsern lassen sich unter Windows nicht auslesen (DPAPI/App-Bound Encryption), deshalb nutzt vd ein eigenes Login-Fenster: braucht eine Seite einen Login, fragt `vd "LINK"` nach; gespeicherte Logins pro Seite (`vd login`, `vd logout SEITE`).
- Bevorzugt einfache Bedienung: wenige Befehle, kurze deutsche Ausgaben, Installation per Einzeiler, Aktualisieren mit `vd update`.
- `vd` ist per `install.ps1` (pip, Benutzer-Installation) installiert; Playwright ist eine normale Abhängigkeit und nutzt das installierte Edge.
- Antworten auf Deutsch.

## Projekt
- Tests: `python -m unittest` (aus dem Repo-Ordner).
- Aufbau: `vd_cli.py` (CLI + gemeinsame Download-Logik `run_download`, die auch die GUI nutzt), `mp4_downloader.py` (GUI), `browser_login.py` (Login-Fenster, gespeicherte Cookies), `page_extractor.py` (eingebettete Videos finden).
- Releases entstehen automatisch, wenn eine neue `version` in `pyproject.toml` (und `__version__` in `vd_cli.py`) auf `main` landet. Optionale Release-Notes: `.github/release-notes/vX.Y.Z.md`. Claude darf keine Releases/Tags direkt anlegen, nur Branches pushen und PRs mergen.
