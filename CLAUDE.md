# Hinweise für Claude

## Umgebung des Besitzers (GamirHD)
- Windows-Rechner, Kommandozeile ist **PowerShell** (Befehle immer für PowerShell angeben, z. B. `Stop-Process -Name brave -Force` statt `taskkill`; `taskkill` ist dort nicht im PATH).
- Browser: **Brave**. Cookies aus Chromium-Browsern lassen sich unter Windows nicht auslesen (DPAPI/App-Bound Encryption), deshalb nutzt vd ein eigenes Login-Fenster: braucht eine Seite einen Login, fragt `vd "LINK"` nach; gespeicherte Logins pro Seite (`vd login`, `vd logout SEITE`).
- Bevorzugt einfache Bedienung: wenige Befehle, kurze deutsche Ausgaben, Installation per Einzeiler, Aktualisieren mit `vd update`.
- Windows-Installation über `mp4-downloader-setup.exe` (Inno Setup, zweisprachig, ohne Admin, nach `%LOCALAPPDATA%\Programs\mp4-downloader`): Programm „Video Downloader“ + `vd.exe` im PATH, Eintrag unter *Apps*. Linux/macOS: `install.sh` (venv, `vd` + `vd-gui`, App-Menü-Eintrag). Releases enthalten nur noch den Windows-Installer. `vd update` lädt dort den neuesten Installer. Playwright ist gebündelt; Login-Fenster und Video-Suche nutzen den Standardbrowser, wenn er Chromium-basiert ist (bei ihm Brave, eigenes Profil), sonst Edge (`browsers.py`).
- ga.gg erlaubt nur eine aktive Sitzung: Login im vd-Fenster wirft ihn in Brave raus. Dafür `vd login --import` (Cookies aus Brave per Erweiterung „Get cookies.txt LOCALLY“ → Copy übernehmen, `cookie_import.py`). Er neigt dazu, Cookie-Dateien/Logins in den Chat zu laden – dann auf Sicherheit hinweisen.
- Antworten auf Deutsch. Das Programm ist standardmäßig Englisch; er nutzt es auf Deutsch (`vd settings --language de`).

## Projekt
- Tests: `python -m unittest` (aus dem Repo-Ordner). Windows-Installer wird in jedem PR von GitHub Actions gebaut und getestet (Installieren, `vd selftest`, Deinstallieren) – vor dem Mergen prüfen.
- HTTP-Login (401, z. B. Uni-Server wie decker.cs.tu-dortmund.de): `site_auth.py` fragt Benutzername/Passwort ab, schickt sie nur an dieselbe Website (Header pro Anfrage, `make_downloader`), speichert sie unter Windows per DPAPI.
- Texte: `i18n.py` (en/de, jeder Schlüssel braucht beide Sprachen – ein Test prüft das). GUI-Screenshots: jeder PR legt sie auf den Branch `ci-screenshots` (Windows, en + de).
- Aufbau: `vd_cli.py` (CLI + gemeinsame Download-Logik `run_download`, die auch die GUI nutzt), `mp4_downloader.py` (GUI), `browser_login.py` (Login-Fenster, gespeicherte Cookies), `page_extractor.py` (eingebettete Videos finden).
- Releases entstehen automatisch, wenn eine neue `version` in `pyproject.toml` (und `__version__` in `vd_cli.py`) auf `main` landet. Optionale Release-Notes: `.github/release-notes/vX.Y.Z.md`. Claude darf keine Releases/Tags direkt anlegen, nur Branches pushen und PRs mergen.
