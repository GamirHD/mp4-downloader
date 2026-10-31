# Hinweise für Claude

## Umgebung des Besitzers (GamirHD)
- Windows-Rechner, Kommandozeile ist **PowerShell** (Befehle immer für PowerShell angeben, z. B. `Stop-Process -Name brave -Force` statt `taskkill`; `taskkill` ist dort nicht im PATH).
- Browser: **Brave**. Cookies aus Chromium-Browsern lassen sich unter Windows nicht auslesen (DPAPI/App-Bound Encryption), deshalb nutzt vd ein eigenes Login-Fenster: braucht eine Seite einen Login, fragt `vd "LINK"` nach; gespeicherte Logins pro Seite (`vd login`, `vd logout SEITE`).
- Bevorzugt einfache Bedienung: wenige Befehle, kurze deutsche Ausgaben, Installation per Einzeiler, Aktualisieren mit `vd update`.
- Windows-Installation über `mp4-downloader-setup.exe` (Inno Setup, ohne Admin, nach `%LOCALAPPDATA%\Programs\mp4-downloader`): Programm mit Oberfläche + `vd.exe` im PATH, Eintrag unter *Apps*. `vd update` lädt dort den neuesten Installer. Playwright ist gebündelt; Login-Fenster und Video-Suche nutzen den Standardbrowser, wenn er Chromium-basiert ist (bei ihm Brave, eigenes Profil), sonst Edge (`browsers.py`).
- Antworten auf Deutsch.

## Projekt
- Tests: `python -m unittest` (aus dem Repo-Ordner). Windows-Installer wird in jedem PR von GitHub Actions gebaut und getestet (Installieren, `vd selftest`, Deinstallieren) – vor dem Mergen prüfen.
- HTTP-Login (401, z. B. Uni-Server wie decker.cs.tu-dortmund.de): `site_auth.py` fragt Benutzername/Passwort ab, schickt sie nur an dieselbe Website (Header pro Anfrage, `make_downloader`), speichert sie unter Windows per DPAPI.
- Aufbau: `vd_cli.py` (CLI + gemeinsame Download-Logik `run_download`, die auch die GUI nutzt), `mp4_downloader.py` (GUI), `browser_login.py` (Login-Fenster, gespeicherte Cookies), `page_extractor.py` (eingebettete Videos finden).
- Releases entstehen automatisch, wenn eine neue `version` in `pyproject.toml` (und `__version__` in `vd_cli.py`) auf `main` landet. Optionale Release-Notes: `.github/release-notes/vX.Y.Z.md`. Claude darf keine Releases/Tags direkt anlegen, nur Branches pushen und PRs mergen.
