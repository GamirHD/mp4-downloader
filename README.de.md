# Video Downloader (`vd`)

Videos per Link als **MP4** oder **MP3** herunterladen – von YouTube und vielen anderen Seiten, auch
von Seiten mit eigenem Video-Player oder Login (z. B. Kursplattformen, Uni-Server). Als Programm mit
Fenster und als Befehl `vd`.

**English:** [README.md](README.md)

## Installation

Ein Befehl installiert das Programm mit Fenster **und** `vd`:

**Windows** (PowerShell) – oder
[`mp4-downloader-setup.exe`](https://github.com/GamirHD/mp4-downloader/releases/latest/download/mp4-downloader-setup.exe)
herunterladen und starten:

```powershell
irm https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.ps1 | iex
```

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/install.sh | bash
```

Danach gibt es **Video Downloader** im Startmenü / App-Menü / Programme-Ordner und den Befehl `vd` in
jedem **neuen** Terminal. Das Programm startet auf Englisch – auf Deutsch umstellen:

```powershell
vd settings --language de
```

(oder im Programm oben rechts bei *Language*). Aktualisieren mit `vd update`.

## Befehle

| Befehl | Was passiert |
| --- | --- |
| `vd "LINK"` | Video als MP4 laden (Standard: bis 1080p) |
| `vd -a "LINK"` | Nur den Ton als MP3 |
| `vd -q 720p "LINK"` | Andere Qualität: `best`, `original`, `1080p`, `720p`, `480p`, `mp3` |
| `vd "LINK1" "LINK2"` | Mehrere Videos nacheinander |
| `vd --playlist "LINK"` | Ganze Playlist |
| `vd -f "D:\Videos" "LINK"` | In einen anderen Ordner |
| `vd settings -f "D:\Videos" -q 720p` | Standard-Ordner und -Qualität ändern |
| `vd history` / `vd update` / `vd --help` | Verlauf / Aktualisieren / Hilfe |

`original` lädt die unbearbeitete Originaldatei, wenn eine Seite sie anbietet (z. B. Kursplattformen mit
Wistia) – die schärfste Version, aber oft mehrere GB groß. Sonst wie `best`.

## Seiten mit Login

Einfach den Link eingeben. Braucht die Seite einen Login, fragt `vd` nach; mit **Enter** öffnet sich
ein Browserfenster (dein Standardbrowser, z. B. Brave – sonst Edge, mit eigenem Profil): einloggen,
Fenster schließen, der Download startet neu. Fragt eine Seite direkt nach **Benutzername und
Passwort** (z. B. Uni-Server), gibst du sie im Terminal ein; sie gehen nur an diese Seite und werden
verschlüsselt gespeichert. `vd login` zeigt gespeicherte Logins, `vd logout SEITE` löscht sie.

**Seiten, die nur einen Login gleichzeitig erlauben** (Einloggen mit vd wirft dich im Browser raus):
Übernimm stattdessen den Login deines Browsers. Im Browser die Seite öffnen (eingeloggt), Erweiterung
*Get cookies.txt LOCALLY* → **Copy**, dann `vd login --import` (oder im Programm *Logins... → Aus Browser
übernehmen*). Die Zwischenablage wird danach geleert. Nur wiederholen, wenn die Seite dich ausloggt.

**Nicht möglich:** kopiergeschützte Videos (DRM), z. B. Netflix, Disney+ oder Prime Video.

## Deinstallieren

Windows: *Einstellungen → Apps → Video Downloader → Deinstallieren*. Linux/macOS:
`curl -fsSL https://raw.githubusercontent.com/GamirHD/mp4-downloader/main/uninstall.sh | bash`
