# mp4-downloader (`vd`)

Videos per Link als **MP4** oder **MP3** herunterladen – von YouTube und vielen anderen Seiten,
auch von Seiten mit eigenem Video-Player oder Login.

```powershell
vd "https://www.youtube.com/watch?v=..."
```

## Installation

**Windows:** [`mp4-downloader-setup.exe`](https://github.com/GamirHD/mp4-downloader/releases/latest/download/mp4-downloader-setup.exe)
herunterladen und starten – oder in PowerShell:

```powershell
irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
```

Danach gibt es im Startmenü den **Video-Downloader** (Programm mit Fenster) und im Terminal den
Befehl **`vd`**. Python wird nicht gebraucht, ffmpeg wird automatisch installiert. Deinstallieren
geht wie bei jedem Programm über *Einstellungen → Apps → Video-Downloader*.

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.sh | bash
```

Danach ein **neues** Terminal öffnen. Aktualisieren geht später mit `vd update`.

## Benutzung

| Befehl | Was passiert |
| --- | --- |
| `vd "LINK"` | Video als MP4 laden (Standard: bis 1080p) |
| `vd -a "LINK"` | Nur den Ton als MP3 |
| `vd -q 720p "LINK"` | Andere Qualität: `best`, `1080p`, `720p`, `480p`, `mp3` |
| `vd "LINK1" "LINK2"` | Mehrere Videos nacheinander |
| `vd --playlist "LINK"` | Ganze Playlist |
| `vd -f "D:\Videos" "LINK"` | In einen anderen Ordner |

Videos landen standardmäßig im **Downloads**-Ordner. Standard-Ordner und -Qualität ändern:

```powershell
vd settings -f "D:\Videos" -q 720p
```

Weitere Befehle: `vd history` (letzte Downloads), `vd update` (vd und yt-dlp aktualisieren),
`vd --help` (alle Optionen).

## Seiten mit Login

Einfach den Link wie immer eingeben. Braucht die Seite einen Login, fragt `vd`:

```
example.com braucht vermutlich einen Login. Jetzt einloggen? [J/n]
```

Mit **Enter** öffnet sich ein Browserfenster (dein Standardbrowser, z. B. Brave oder Chrome –
sonst Edge): einloggen, Fenster schließen – der Download startet automatisch neu. Das Fenster
nutzt ein eigenes Profil, deine normalen Browser-Logins bleiben unberührt. Der Login wird pro Seite gespeichert und beim nächsten Mal von selbst verwendet.

```powershell
vd login            # Seiten mit gespeichertem Login anzeigen
vd login "LINK"     # vorab einloggen
vd logout SEITE     # Login einer Seite löschen (ohne SEITE: alle)
```

Manche Seiten (z. B. Uni-Server) fragen statt einer Login-Seite direkt nach **Benutzername und
Passwort**. Dann fragt `vd` im Terminal danach (das Passwort wird nicht angezeigt). Die Zugangsdaten
werden nur an diese eine Seite geschickt und unter Windows verschlüsselt für dein Windows-Konto
gespeichert.

Logins liegen nur in den Programm-Einstellungen (Windows: `%APPDATA%\mp4-downloader`),
nie im Download-Ordner.

**Nicht möglich:** Videos mit Kopierschutz (DRM), z. B. Netflix, Disney+ oder Prime Video –
auch nicht mit Login. `vd` sagt das dann direkt.

## Programm mit Oberfläche

Unter Windows im Startmenü **Video-Downloader** öffnen (nach einer Installation über Linux/macOS:
`vd-gui`): Links einfügen, Qualität und Ordner wählen, fertig. Login-Abfragen funktionieren dort
genauso.

## Deinstallieren

Windows: *Einstellungen → Apps → Video-Downloader → Deinstallieren* (entfernt Programm und `vd`).

Linux/macOS: `curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.sh | bash`

## Für Entwickler

```bash
python -m pip install -e .
python -m unittest
```

Den Windows-Installer baut `build-windows.ps1` (PyInstaller + Inno Setup). Jeder Pull Request baut
ihn auf einem Windows-Rechner bei GitHub und testet Installation, `vd` und Deinstallation.

Releases entstehen automatisch, sobald eine neue `version` in `pyproject.toml` auf `main` landet
(optionale Notizen in `.github/release-notes/vX.Y.Z.md`).
