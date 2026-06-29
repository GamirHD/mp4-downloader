from __future__ import annotations

import os
import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

try:
    import yt_dlp
except ImportError:  # pragma: no cover - handled in GUI startup
    yt_dlp = None


APP_TITLE = "MP4/MP3 Downloader"


QUALITY_OPTIONS = {
    "Beste Qualitaet": ("bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best", "mp4"),
    "1080p": ("bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080]", "mp4"),
    "720p": ("bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]", "mp4"),
    "480p": ("bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]", "mp4"),
    "MP3": ("bestaudio/best", "mp3"),
}


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

        self.url_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.quality_var = tk.StringVar(value="Beste Qualitaet")
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

        url_frame = ttk.LabelFrame(root, text="Video-Link", padding=12)
        url_frame.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        url_frame.columnconfigure(0, weight=1)
        ttk.Entry(url_frame, textvariable=self.url_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(url_frame, text="Einfuegen", command=self._paste_url).grid(row=0, column=1, padx=(10, 0))

        options = ttk.Frame(root)
        options.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Qualitaet").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=list(QUALITY_OPTIONS.keys()),
            state="readonly",
            width=22,
        ).grid(row=0, column=1, sticky="w", padx=(10, 20))

        ttk.Label(options, text="Ordner").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(options, textvariable=self.folder_var).grid(row=1, column=1, sticky="ew", padx=(10, 10), pady=(10, 0))
        ttk.Button(options, text="Waehlen", command=self._choose_folder).grid(row=1, column=2, pady=(10, 0))

        action_frame = ttk.Frame(root)
        action_frame.grid(row=3, column=0, sticky="ew", pady=(2, 10))
        action_frame.columnconfigure(1, weight=1)
        self.download_button = ttk.Button(action_frame, text="Download starten", command=self._start_download)
        self.download_button.grid(row=0, column=0, sticky="w")
        ttk.Label(action_frame, textvariable=self.status_var).grid(row=0, column=1, sticky="e")

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
            self.url_var.set(self.clipboard_get().strip())
        except tk.TclError:
            self._log("Zwischenablage ist leer.")

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if folder:
            self.folder_var.set(folder)

    def _start_download(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            return

        url = self.url_var.get().strip()
        folder = Path(self.folder_var.get()).expanduser()
        quality = self.quality_var.get()

        if yt_dlp is None:
            messagebox.showerror(APP_TITLE, "yt-dlp ist nicht installiert.")
            return
        if not url:
            messagebox.showwarning(APP_TITLE, "Bitte einen Video-Link einfuegen.")
            return
        if not folder:
            messagebox.showwarning(APP_TITLE, "Bitte einen Download-Ordner auswaehlen.")
            return

        folder.mkdir(parents=True, exist_ok=True)
        self.progress_var.set(0)
        self.status_var.set("Download laeuft...")
        self.download_button.configure(state="disabled")
        self._log(f"Starte Download: {url}")

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(url, folder, QUALITY_OPTIONS[quality]),
            daemon=True,
        )
        self.download_thread.start()

    def _download_worker(self, url: str, folder: Path, quality: tuple[str, str]) -> None:
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

        format_selector, output_kind = quality
        ffmpeg_path = shutil.which("ffmpeg")
        ydl_opts: dict[str, Any] = {
            "format": format_selector,
            "outtmpl": str(folder / "%(title).200s [%(id)s].%(ext)s"),
            "noplaylist": True,
            "progress_hooks": [hook],
            "logger": QueueLogger(self.messages),
            "quiet": False,
            "no_warnings": False,
        }
        if output_kind == "mp4":
            ydl_opts["merge_output_format"] = "mp4"
        if output_kind == "mp3":
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_path)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as downloader:
                info = downloader.extract_info(url, download=True)
            title = info.get("title", "Video") if isinstance(info, dict) else "Video"
            self.messages.put(("done", f"Fertig: {title}"))
        except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
            self.messages.put(("error", self._friendly_error(str(exc))))

    def _friendly_error(self, raw_error: str) -> str:
        text = raw_error.strip()
        lower = text.lower()
        if "sign in to confirm" in lower or "bot" in lower or "cookies" in lower:
            return (
                "YouTube verlangt fuer diesen Link eine Browser-Session oder blockiert den Zugriff. "
                "Teste ein anderes Video oder nutze die App auf deinem eigenen PC mit normalem Netzwerk."
            )
        if "ffmpeg" in lower:
            return "ffmpeg fehlt oder wurde nicht gefunden. Bitte ffmpeg installieren und danach erneut starten."
        if "unsupported url" in lower:
            return "Dieser Link wird nicht unterstuetzt. Bitte pruefe die URL."
        return text

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
