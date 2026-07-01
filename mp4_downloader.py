from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from vd_cli import BROWSER_CHOICES, QUALITY_OPTIONS, build_ydl_options, friendly_error, load_settings, save_settings

try:
    import yt_dlp
except ImportError:  # pragma: no cover - handled in GUI startup
    yt_dlp = None


APP_TITLE = "MP4/MP3 Downloader"


GUI_QUALITY_KEYS = list(QUALITY_OPTIONS)
GUI_QUALITY_LABELS = {key: values[0] for key, values in QUALITY_OPTIONS.items()}
GUI_QUALITY_CHOICES = [f"{key} - {GUI_QUALITY_LABELS[key]}" for key in GUI_QUALITY_KEYS]
BROWSER_COOKIE_CHOICES = ["Keine"] + list(BROWSER_CHOICES)


class QueueLogger:
    def __init__(self, messages: queue.Queue[tuple[str, Any]]) -> None:
        self.messages = messages

    def debug(self, message: str) -> None:
        if message.startswith("[debug]"):
            return
        self.messages.put(("log", message))

    def info(self, message: str) -> None:
        self.messages.put(("log", message))

    def warning(self, message: str) -> None:
        self.messages.put(("log", f"Warnung: {message}"))

    def error(self, message: str) -> None:
        self.messages.put(("log", f"Fehler: {message}"))


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x520")
        self.minsize(680, 460)

        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.download_thread: threading.Thread | None = None
        self.settings = load_settings()

        self.folder_var = tk.StringVar(value=self.settings["download_dir"])
        self.quality_var = tk.StringVar(value=GUI_QUALITY_CHOICES[0])
        self.cookies_var = tk.StringVar(value="Keine")
        self.playlist_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Bereit")
        self.progress_var = tk.DoubleVar(value=0)

        self._build_ui()
        self.after(100, self._poll_messages)

        if yt_dlp is None:
            self._set_idle_error("yt-dlp ist nicht installiert. Bitte `pip install -r requirements.txt` ausfuehren.")

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        root = ttk.Frame(self, padding=18)
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(5, weight=1)

        title = ttk.Label(root, text=APP_TITLE, font=("TkDefaultFont", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")

        url_frame = ttk.LabelFrame(root, text="Video-Links", padding=12)
        url_frame.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        url_frame.columnconfigure(0, weight=1)
        self.url_text = tk.Text(url_frame, height=4, wrap="word")
        self.url_text.grid(row=0, column=0, sticky="ew")
        ttk.Button(url_frame, text="Einfuegen", command=self._paste_url).grid(row=0, column=1, sticky="n", padx=(10, 0))

        options = ttk.Frame(root)
        options.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Qualitaet").grid(row=0, column=0, sticky="w")
        quality_box = ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=GUI_QUALITY_CHOICES,
            state="readonly",
            width=22,
        )
        quality_box.grid(row=0, column=1, sticky="w", padx=(10, 20))

        ttk.Label(options, text="Browser-Cookies").grid(row=0, column=2, sticky="w")
        cookies_box = ttk.Combobox(
            options,
            textvariable=self.cookies_var,
            values=BROWSER_COOKIE_CHOICES,
            state="readonly",
            width=14,
        )
        cookies_box.grid(row=0, column=3, sticky="w", padx=(10, 0))

        ttk.Label(options, text="Ordner").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(options, textvariable=self.folder_var).grid(row=1, column=1, sticky="ew", padx=(10, 10), pady=(10, 0))
        ttk.Button(options, text="Waehlen", command=self._choose_folder).grid(row=1, column=2, pady=(10, 0))
        ttk.Button(options, text="Oeffnen", command=self._open_folder).grid(row=1, column=3, padx=(8, 0), pady=(10, 0))
        ttk.Checkbutton(
            options,
            text="Playlist komplett herunterladen",
            variable=self.playlist_var,
        ).grid(row=2, column=1, columnspan=3, sticky="w", padx=(10, 0), pady=(10, 0))

        action_frame = ttk.Frame(root)
        action_frame.grid(row=3, column=0, sticky="ew", pady=(2, 10))
        action_frame.columnconfigure(2, weight=1)
        self.download_button = ttk.Button(action_frame, text="Download starten", command=self._start_download)
        self.download_button.grid(row=0, column=0, sticky="w")
        ttk.Button(action_frame, text="Log leeren", command=self._clear_log).grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(action_frame, textvariable=self.status_var).grid(row=0, column=2, sticky="e")

        self.progress = ttk.Progressbar(root, variable=self.progress_var, maximum=100)
        self.progress.grid(row=4, column=0, sticky="ew", pady=(0, 12))

        log_frame = ttk.LabelFrame(root, text="Status", padding=8)
        log_frame.grid(row=5, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _paste_url(self) -> None:
        try:
            text = self.clipboard_get().strip()
            if not text:
                self._log("Zwischenablage ist leer.")
                return
            if self.url_text.get("1.0", "end").strip():
                self.url_text.insert("end", "\n")
            self.url_text.insert("end", text)
        except tk.TclError:
            self._log("Zwischenablage ist leer.")

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if folder:
            self.folder_var.set(folder)
            self.settings["download_dir"] = folder
            save_settings(self.settings)
            self._log(f"Downloadordner gespeichert: {folder}")

    def _open_folder(self) -> None:
        folder = Path(self.folder_var.get()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:  # noqa: BLE001 - OS integration boundary
            messagebox.showerror(APP_TITLE, f"Ordner kann nicht geoeffnet werden:\n{exc}")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _start_download(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            return

        urls = self._read_urls()
        folder = Path(self.folder_var.get()).expanduser()
        quality = self.quality_var.get().split(" - ", 1)[0]
        cookies_from_browser = self.cookies_var.get()
        allow_playlist = self.playlist_var.get()
        if cookies_from_browser == "Keine":
            cookies_from_browser = None

        if yt_dlp is None:
            messagebox.showerror(APP_TITLE, "yt-dlp ist nicht installiert.")
            return
        if not urls:
            messagebox.showwarning(APP_TITLE, "Bitte mindestens einen Video-Link einfuegen.")
            return
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Download-Ordner kann nicht erstellt werden:\n{exc}")
            return

        self.settings["download_dir"] = str(folder)
        save_settings(self.settings)
        self.progress_var.set(0)
        self.status_var.set("Download laeuft...")
        self.download_button.configure(state="disabled")
        if len(urls) == 1:
            self._log(f"Starte Download: {urls[0]}")
        else:
            self._log(f"Starte Batch-Download mit {len(urls)} Links.")

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(urls, folder, quality, allow_playlist, cookies_from_browser),
            daemon=True,
        )
        self.download_thread.start()

    def _read_urls(self) -> list[str]:
        text = self.url_text.get("1.0", "end")
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _download_worker(
        self,
        urls: list[str],
        folder: Path,
        quality_key: str,
        allow_playlist: bool,
        cookies_from_browser: str | None,
    ) -> None:
        def hook(data: dict[str, Any]) -> None:
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                downloaded = data.get("downloaded_bytes") or 0
                if total:
                    self.messages.put(("progress", min(downloaded / total * 100, 100)))
                speed = data.get("_speed_str", "").strip()
                eta = data.get("_eta_str", "").strip()
                self.messages.put(("status", f"Laedt herunter... {speed} ETA {eta}".strip()))
            elif status == "finished":
                self.messages.put(("progress", 100))
                self.messages.put(("status", "Verarbeite Datei..."))
                filename = data.get("filename")
                if filename:
                    self.messages.put(("log", f"Heruntergeladen: {filename}"))

        ydl_opts = build_ydl_options(
            quality_key,
            folder,
            allow_playlist=allow_playlist,
            cookies_from_browser=cookies_from_browser,
            progress_hooks=[hook],
            logger=QueueLogger(self.messages),
        )

        failures: list[str] = []
        for index, url in enumerate(urls, start=1):
            if len(urls) > 1:
                self.messages.put(("log", f"[{index}/{len(urls)}] {url}"))
                self.messages.put(("status", f"Download {index} von {len(urls)} laeuft..."))
            elif allow_playlist:
                self.messages.put(("log", "Playlist-Modus aktiviert."))
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as downloader:
                    info = downloader.extract_info(url, download=True)
                title = info.get("title", "Video") if isinstance(info, dict) else "Video"
                self.messages.put(("log", f"Fertig: {title}"))
            except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
                message = friendly_error(str(exc))
                failures.append(url)
                self.messages.put(("log", f"Fehler bei {url}: {message}"))

        if failures:
            self.messages.put(("batch_error", f"{len(failures)} von {len(urls)} Downloads fehlgeschlagen."))
            return

        if len(urls) == 1:
            self.messages.put(("done", "Download fertig."))
        else:
            self.messages.put(("done", f"Batch fertig: {len(urls)} Downloads abgeschlossen."))

    def _poll_messages(self) -> None:
        while True:
            try:
                message_type, payload = self.messages.get_nowait()
            except queue.Empty:
                break

            if message_type == "log":
                self._log(str(payload))
            elif message_type == "progress":
                self.progress_var.set(float(payload))
            elif message_type == "status":
                self.status_var.set(str(payload))
            elif message_type == "done":
                self._log(str(payload))
                self.status_var.set("Fertig")
                self.download_button.configure(state="normal")
            elif message_type == "batch_error":
                self._log(f"Fehler: {payload}")
                self.status_var.set("Fertig mit Fehlern")
                self.download_button.configure(state="normal")
                messagebox.showerror(APP_TITLE, str(payload))
            elif message_type == "error":
                self._set_idle_error(str(payload))

        self.after(100, self._poll_messages)

    def _set_idle_error(self, message: str) -> None:
        self._log(f"Fehler: {message}")
        self.status_var.set("Fehler")
        self.download_button.configure(state="normal")
        messagebox.showerror(APP_TITLE, message)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
