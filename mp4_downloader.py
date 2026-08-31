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

from vd_cli import (
    BROWSER_CHOICES,
    QUALITY_OPTIONS,
    add_history_entry,
    build_ydl_options,
    clear_history,
    download_archive_path,
    extract_urls_from_text,
    format_history_timestamp,
    friendly_error,
    history_path,
    load_history,
    load_settings,
    no_urls_found_message,
    save_settings,
)

try:
    import yt_dlp
except ImportError:  # pragma: no cover - handled in GUI startup
    yt_dlp = None


APP_TITLE = "MP4/MP3 Downloader"

BG_COLOR = "#f4f7fb"
SURFACE_COLOR = "#ffffff"
BORDER_COLOR = "#d9e2ec"
TEXT_COLOR = "#172033"
MUTED_TEXT_COLOR = "#64748b"
PRIMARY_COLOR = "#2563eb"
PRIMARY_HOVER_COLOR = "#1d4ed8"
SECONDARY_COLOR = "#e8eef7"
SECONDARY_HOVER_COLOR = "#dbe7f6"
SELECTION_COLOR = "#dbeafe"


GUI_QUALITY_KEYS = list(QUALITY_OPTIONS)
GUI_QUALITY_LABELS = {key: values[0] for key, values in QUALITY_OPTIONS.items()}
GUI_QUALITY_CHOICES = [f"{key} - {GUI_QUALITY_LABELS[key]}" for key in GUI_QUALITY_KEYS]
BROWSER_COOKIE_CHOICES = ["Keine"] + list(BROWSER_CHOICES)


def enable_high_dpi_rendering() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class DownloadCancelled(RuntimeError):
    pass


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
        self._configure_tk_scaling()
        self.title(APP_TITLE)
        self.geometry("720x560")
        self.minsize(640, 500)

        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.download_thread: threading.Thread | None = None
        self.cancel_requested = threading.Event()
        self.settings = load_settings()

        self.folder_var = tk.StringVar(value=self.settings["download_dir"])
        self.quality_var = tk.StringVar(value=GUI_QUALITY_CHOICES[0])
        self.cookies_var = tk.StringVar(value="Keine")
        self.playlist_var = tk.BooleanVar(value=False)
        self.archive_var = tk.BooleanVar(value=bool(self.settings["use_download_archive"]))
        self.status_var = tk.StringVar(value="Bereit")
        self.progress_var = tk.DoubleVar(value=0)
        self.options_visible = tk.BooleanVar(value=False)
        self.options_button_text = tk.StringVar(value="Optionen anzeigen")

        self._build_ui()
        self.after(100, self._poll_messages)

        if yt_dlp is None:
            self._set_idle_error("yt-dlp ist nicht installiert. Bitte `pip install -r requirements.txt` ausfuehren.")

    def _configure_tk_scaling(self) -> None:
        try:
            pixels_per_inch = float(self.winfo_fpixels("1i"))
        except tk.TclError:
            return
        if pixels_per_inch > 0:
            self.tk.call("tk", "scaling", max(1.0, pixels_per_inch / 72.0))

    def _configure_style(self) -> None:
        self.configure(bg=BG_COLOR)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = ("TkDefaultFont", 10)
        style.configure(".", font=default_font, background=BG_COLOR, foreground=TEXT_COLOR)
        style.configure("App.TFrame", background=BG_COLOR)
        style.configure("Surface.TFrame", background=SURFACE_COLOR)
        style.configure("App.TLabel", background=BG_COLOR, foreground=TEXT_COLOR)
        style.configure("Surface.TLabel", background=SURFACE_COLOR, foreground=TEXT_COLOR)
        style.configure("Title.TLabel", background=BG_COLOR, foreground=TEXT_COLOR, font=("TkDefaultFont", 18, "bold"))
        style.configure("Muted.TLabel", background=BG_COLOR, foreground=MUTED_TEXT_COLOR)
        style.configure(
            "TButton",
            background=SECONDARY_COLOR,
            bordercolor=BORDER_COLOR,
            focusthickness=1,
            focuscolor=PRIMARY_COLOR,
            padding=(12, 7),
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", SECONDARY_HOVER_COLOR), ("disabled", "#eef2f7")],
            foreground=[("disabled", "#94a3b8")],
        )
        style.configure(
            "Primary.TButton",
            background=PRIMARY_COLOR,
            foreground="#ffffff",
            bordercolor=PRIMARY_COLOR,
            padding=(16, 8),
            relief="flat",
        )
        style.map(
            "Primary.TButton",
            background=[("active", PRIMARY_HOVER_COLOR), ("disabled", "#93c5fd")],
            foreground=[("disabled", "#eef6ff")],
        )
        style.configure(
            "TEntry",
            fieldbackground=SURFACE_COLOR,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            padding=(8, 7),
        )
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE_COLOR,
            background=SURFACE_COLOR,
            bordercolor=BORDER_COLOR,
            arrowcolor=MUTED_TEXT_COLOR,
            padding=(8, 5),
        )
        style.map("TCombobox", fieldbackground=[("readonly", SURFACE_COLOR)])
        style.configure(
            "TNotebook",
            background=BG_COLOR,
            borderwidth=0,
            tabmargins=(0, 8, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=SECONDARY_COLOR,
            foreground=MUTED_TEXT_COLOR,
            padding=(14, 8),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", SURFACE_COLOR), ("active", SECONDARY_HOVER_COLOR)],
            foreground=[("selected", TEXT_COLOR)],
        )
        style.configure(
            "TProgressbar",
            background=PRIMARY_COLOR,
            troughcolor="#e2e8f0",
            bordercolor="#e2e8f0",
            lightcolor=PRIMARY_COLOR,
            darkcolor=PRIMARY_COLOR,
        )
        style.configure("TCheckbutton", background=BG_COLOR, foreground=TEXT_COLOR)
        style.configure("Surface.TCheckbutton", background=SURFACE_COLOR, foreground=TEXT_COLOR)

    def _build_ui(self) -> None:
        self._configure_style()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        root = ttk.Frame(self, padding=18, style="App.TFrame")
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

        title = ttk.Label(root, text=APP_TITLE, style="Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        url_frame = ttk.Frame(root, padding=(0, 14, 0, 0), style="App.TFrame")
        url_frame.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        url_frame.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda _event: self._add_url())
        ttk.Button(url_frame, text="Einfuegen", command=self._paste_url).grid(row=0, column=1, sticky="ew", padx=(10, 0))
        ttk.Button(url_frame, text="Hinzufuegen", command=self._add_url).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        queue_frame = ttk.Frame(url_frame, style="App.TFrame")
        queue_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)

        self.url_listbox = self._create_listbox(queue_frame, height=4)
        self.url_listbox.grid(row=0, column=0, rowspan=2, sticky="ew")
        self.url_listbox.bind("<Delete>", lambda _event: self._remove_selected_urls())
        queue_scrollbar = ttk.Scrollbar(queue_frame, command=self.url_listbox.yview)
        queue_scrollbar.grid(row=0, column=1, rowspan=2, sticky="ns")
        self.url_listbox.configure(yscrollcommand=queue_scrollbar.set)

        queue_buttons = ttk.Frame(queue_frame, style="App.TFrame")
        queue_buttons.grid(row=0, column=2, sticky="n", padx=(10, 0))
        ttk.Button(queue_buttons, text="Entfernen", command=self._remove_selected_urls).grid(row=0, column=0, sticky="ew")
        ttk.Button(queue_buttons, text="Leeren", command=self._clear_urls).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(queue_buttons, text="Hoch", command=lambda: self._move_selected_url(-1)).grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(queue_buttons, text="Runter", command=lambda: self._move_selected_url(1)).grid(row=3, column=0, sticky="ew", pady=(6, 0))

        primary_frame = ttk.Frame(root, style="App.TFrame")
        primary_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        primary_frame.columnconfigure(2, weight=1)
        self.download_button = ttk.Button(
            primary_frame,
            text="Download starten",
            command=self._start_download,
            style="Primary.TButton",
        )
        self.download_button.grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(primary_frame, text="Abbrechen", command=self._cancel_download, state="disabled")
        self.cancel_button.grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(primary_frame, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=2, sticky="e")

        self.progress = ttk.Progressbar(root, variable=self.progress_var, maximum=100)
        self.progress.grid(row=3, column=0, sticky="ew", pady=(0, 12))

        secondary = ttk.Notebook(root)
        secondary.grid(row=4, column=0, sticky="nsew")

        settings_tab = ttk.Frame(secondary, padding=10, style="Surface.TFrame")
        history_tab = ttk.Frame(secondary, padding=10, style="Surface.TFrame")
        log_tab = ttk.Frame(secondary, padding=10, style="Surface.TFrame")
        secondary.add(settings_tab, text="Einstellungen")
        secondary.add(history_tab, text="Verlauf")
        secondary.add(log_tab, text="Status")

        settings_tab.columnconfigure(0, weight=1)
        ttk.Button(
            settings_tab,
            textvariable=self.options_button_text,
            command=self._toggle_options,
        ).grid(row=0, column=0, sticky="w")

        options = ttk.Frame(settings_tab, style="Surface.TFrame")
        self.options_frame = options
        options.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Qualitaet", style="Surface.TLabel").grid(row=0, column=0, sticky="w")
        quality_box = ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=GUI_QUALITY_CHOICES,
            state="readonly",
            width=22,
        )
        quality_box.grid(row=0, column=1, sticky="w", padx=(10, 20))

        ttk.Label(options, text="Browser-Cookies", style="Surface.TLabel").grid(row=0, column=2, sticky="w")
        cookies_box = ttk.Combobox(
            options,
            textvariable=self.cookies_var,
            values=BROWSER_COOKIE_CHOICES,
            state="readonly",
            width=14,
        )
        cookies_box.grid(row=0, column=3, sticky="w", padx=(10, 0))

        ttk.Label(options, text="Ordner", style="Surface.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(options, textvariable=self.folder_var).grid(row=1, column=1, sticky="ew", padx=(10, 10), pady=(10, 0))
        ttk.Button(options, text="Waehlen", command=self._choose_folder).grid(row=1, column=2, pady=(10, 0))
        ttk.Button(options, text="Oeffnen", command=self._open_folder).grid(row=1, column=3, padx=(8, 0), pady=(10, 0))
        ttk.Checkbutton(
            options,
            text="Playlist komplett herunterladen",
            variable=self.playlist_var,
            style="Surface.TCheckbutton",
        ).grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(10, 0))
        ttk.Checkbutton(
            options,
            text="Bereits heruntergeladene Videos ueberspringen",
            variable=self.archive_var,
            command=self._save_archive_setting,
            style="Surface.TCheckbutton",
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(10, 0))
        self._toggle_options(force=False)

        history_frame = ttk.Frame(history_tab, style="Surface.TFrame")
        history_frame.grid(row=0, column=0, sticky="nsew")
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)
        history_tab.columnconfigure(0, weight=1)
        history_tab.rowconfigure(0, weight=1)

        self.history_listbox = self._create_listbox(history_frame, height=4)
        self.history_listbox.grid(row=0, column=0, sticky="nsew")
        self.history_listbox.bind("<Double-Button-1>", lambda _event: self._add_selected_history_urls())
        history_scrollbar = ttk.Scrollbar(history_frame, command=self.history_listbox.yview)
        history_scrollbar.grid(row=0, column=1, sticky="ns")
        self.history_listbox.configure(yscrollcommand=history_scrollbar.set)

        history_buttons = ttk.Frame(history_frame, style="Surface.TFrame")
        history_buttons.grid(row=0, column=2, sticky="n", padx=(10, 0))
        ttk.Button(history_buttons, text="Erneut hinzufuegen", command=self._add_selected_history_urls).grid(row=0, column=0, sticky="ew")
        ttk.Button(history_buttons, text="Aktualisieren", command=self._refresh_history).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(history_buttons, text="Verlauf loeschen", command=self._clear_history).grid(row=2, column=0, sticky="ew", pady=(6, 0))

        log_frame = ttk.Frame(log_tab, style="Surface.TFrame")
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap="word",
            state="disabled",
            background=SURFACE_COLOR,
            foreground=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            selectbackground=SELECTION_COLOR,
            selectforeground=TEXT_COLOR,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        ttk.Button(log_tab, text="Log leeren", command=self._clear_log).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._refresh_history()

    def _create_listbox(self, parent: tk.Misc, height: int) -> tk.Listbox:
        return tk.Listbox(
            parent,
            height=height,
            activestyle="none",
            selectmode="extended",
            background=SURFACE_COLOR,
            foreground=TEXT_COLOR,
            selectbackground=SELECTION_COLOR,
            selectforeground=TEXT_COLOR,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
            relief="flat",
            borderwidth=0,
        )

    def _toggle_options(self, force: bool | None = None) -> None:
        visible = not self.options_visible.get() if force is None else force
        self.options_visible.set(visible)
        if visible:
            self.options_frame.grid()
            self.options_button_text.set("Optionen ausblenden")
        else:
            self.options_frame.grid_remove()
            self.options_button_text.set("Optionen anzeigen")

    def _paste_url(self) -> None:
        try:
            text = self.clipboard_get().strip()
            if not text:
                self._log("Zwischenablage ist leer.")
                return
            self._add_urls_from_text(text)
        except tk.TclError:
            self._log("Zwischenablage ist leer.")

    def _add_url(self) -> None:
        text = self.url_entry.get().strip()
        if not text:
            return
        self._add_urls_from_text(text)
        self.url_entry.delete(0, "end")

    def _add_urls_from_text(self, text: str) -> None:
        urls = extract_urls_from_text(text)
        if not urls:
            self._log(no_urls_found_message())
            return
        existing = set(self._read_urls())
        added = 0
        for url in urls:
            if url in existing:
                continue
            self.url_listbox.insert("end", url)
            existing.add(url)
            added += 1
        if added:
            label = "Link" if added == 1 else "Links"
            self._log(f"{added} {label} zur Warteschlange hinzugefuegt.")
        else:
            self._log("Keine neuen Links hinzugefuegt.")

    def _remove_selected_urls(self) -> None:
        selected = list(self.url_listbox.curselection())
        if not selected:
            return
        for index in reversed(selected):
            self.url_listbox.delete(index)
        self._log(f"{len(selected)} Link(s) aus der Warteschlange entfernt.")

    def _clear_urls(self) -> None:
        if self.url_listbox.size() == 0:
            return
        self.url_listbox.delete(0, "end")
        self._log("Warteschlange geleert.")

    def _move_selected_url(self, direction: int) -> None:
        selected = self.url_listbox.curselection()
        if len(selected) != 1:
            return
        index = selected[0]
        new_index = index + direction
        if new_index < 0 or new_index >= self.url_listbox.size():
            return
        url = self.url_listbox.get(index)
        self.url_listbox.delete(index)
        self.url_listbox.insert(new_index, url)
        self.url_listbox.selection_set(new_index)
        self.url_listbox.activate(new_index)

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if folder:
            self.folder_var.set(folder)
            self.settings["download_dir"] = folder
            save_settings(self.settings)
            self._log(f"Downloadordner gespeichert: {folder}")

    def _save_archive_setting(self) -> None:
        self.settings["use_download_archive"] = self.archive_var.get()
        save_settings(self.settings)
        state = "aktiviert" if self.archive_var.get() else "deaktiviert"
        self._log(f"Download-Archiv {state}: {download_archive_path()}")

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

        pending_text = self.url_entry.get().strip()
        if pending_text:
            self._add_urls_from_text(pending_text)
            self.url_entry.delete(0, "end")

        urls = self._read_urls()
        folder = Path(self.folder_var.get()).expanduser()
        quality = self.quality_var.get().split(" - ", 1)[0]
        cookies_from_browser = self.cookies_var.get()
        allow_playlist = self.playlist_var.get()
        use_download_archive = self.archive_var.get()
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
        self.settings["use_download_archive"] = use_download_archive
        save_settings(self.settings)
        self.cancel_requested.clear()
        self.progress_var.set(0)
        self.status_var.set("Download laeuft...")
        self.download_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        if len(urls) == 1:
            self._log(f"Starte Download: {urls[0]}")
        else:
            self._log(f"Starte Batch-Download mit {len(urls)} Links.")
        if use_download_archive:
            self._log(f"Download-Archiv aktiv: {download_archive_path()}")

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(urls, folder, quality, allow_playlist, cookies_from_browser, use_download_archive),
            daemon=True,
        )
        self.download_thread.start()

    def _cancel_download(self) -> None:
        if not self.download_thread or not self.download_thread.is_alive():
            return
        if self.cancel_requested.is_set():
            return
        self.cancel_requested.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Abbruch wird vorbereitet...")
        self._log("Abbruch angefordert. Der aktuelle Download wird gestoppt.")

    def _read_urls(self) -> list[str]:
        return [str(self.url_listbox.get(index)).strip() for index in range(self.url_listbox.size())]

    def _refresh_history(self) -> None:
        self.history_entries = load_history()
        self.history_listbox.delete(0, "end")
        for entry in self.history_entries[:20]:
            title = entry.get("title") or "Video"
            quality = entry.get("quality") or "?"
            downloaded_at = str(entry.get("downloaded_at") or "")
            shown_time = format_history_timestamp(downloaded_at) if downloaded_at else "?"
            self.history_listbox.insert("end", f"{shown_time} | {quality} | {title}")

    def _add_selected_history_urls(self) -> None:
        selected = self.history_listbox.curselection()
        if not selected:
            return
        urls = []
        for index in selected:
            if index < len(self.history_entries):
                url = self.history_entries[index].get("url")
                if url:
                    urls.append(str(url))
        self._add_urls_from_text("\n".join(urls))

    def _clear_history(self) -> None:
        if not messagebox.askyesno(APP_TITLE, "Download-Verlauf wirklich loeschen?"):
            return
        clear_history()
        self._refresh_history()
        self._log(f"Download-Verlauf geloescht: {history_path()}")

    def _download_worker(
        self,
        urls: list[str],
        folder: Path,
        quality_key: str,
        allow_playlist: bool,
        cookies_from_browser: str | None,
        use_download_archive: bool,
    ) -> None:
        if allow_playlist:
            self.messages.put(("log", "Playlist-Modus aktiviert."))

        def hook(data: dict[str, Any]) -> None:
            if self.cancel_requested.is_set():
                raise DownloadCancelled("Download abgebrochen.")
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
            use_download_archive=use_download_archive,
            progress_hooks=[hook],
            logger=QueueLogger(self.messages),
        )

        failures: list[str] = []
        for index, url in enumerate(urls, start=1):
            if self.cancel_requested.is_set():
                self.messages.put(("cancelled", "Download abgebrochen."))
                return
            if len(urls) > 1:
                self.messages.put(("log", f"[{index}/{len(urls)}] {url}"))
                self.messages.put(("status", f"Download {index} von {len(urls)} laeuft..."))
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as downloader:
                    info = downloader.extract_info(url, download=True)
                title = info.get("title", "Video") if isinstance(info, dict) else "Video"
                add_history_entry(url, title=title, quality_key=quality_key, folder=folder)
                self.messages.put(("history_changed", None))
                self.messages.put(("log", f"Fertig: {title}"))
            except DownloadCancelled:
                self.messages.put(("cancelled", "Download abgebrochen."))
                return
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
            elif message_type == "history_changed":
                self._refresh_history()
            elif message_type == "done":
                self._log(str(payload))
                self.status_var.set("Fertig")
                self.download_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
            elif message_type == "cancelled":
                self._log(str(payload))
                self.status_var.set("Abgebrochen")
                self.download_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
            elif message_type == "batch_error":
                self._log(f"Fehler: {payload}")
                self.status_var.set("Fertig mit Fehlern")
                self.download_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
                messagebox.showerror(APP_TITLE, str(payload))
            elif message_type == "error":
                self._set_idle_error(str(payload))

        self.after(100, self._poll_messages)

    def _set_idle_error(self, message: str) -> None:
        self._log(f"Fehler: {message}")
        self.status_var.set("Fehler")
        self.download_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        messagebox.showerror(APP_TITLE, message)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    enable_high_dpi_rendering()
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
