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

from browser_login import BrowserLoginError, interactive_login, saved_cookies_for, site_of
from cookie_input import CookieInputError, cookies_text_to_netscape, temporary_cookie_file
from vd_cli import (
    BROWSER_CHOICES,
    QUALITY_OPTIONS,
    add_history_entry,
    build_ydl_options,
    download_url,
    login_might_help,
    login_profile_dir,
    saved_login_cookie_text,
    extract_urls_from_text,
    friendly_error,
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
GUI_QUALITY_CHOICES = [GUI_QUALITY_LABELS[key] for key in GUI_QUALITY_KEYS]
GUI_QUALITY_BY_LABEL = dict(zip(GUI_QUALITY_CHOICES, GUI_QUALITY_KEYS))
GUI_NO_BROWSER_LABEL = "Automatisch (gespeicherter Login)"
GUI_CLIPBOARD_LABEL = "Aus Zwischenablage (cookies.txt)"
GUI_BROWSER_CHOICES = [
    GUI_NO_BROWSER_LABEL,
    GUI_CLIPBOARD_LABEL,
    *(name.capitalize() for name in BROWSER_CHOICES),
]
GUI_BROWSER_BY_LABEL = {name.capitalize(): name for name in BROWSER_CHOICES}


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
        saved_browser = self.settings.get("cookies_from_browser")
        if self.settings.get("cookies_from_clipboard"):
            initial_login = GUI_CLIPBOARD_LABEL
        elif saved_browser:
            initial_login = saved_browser.capitalize()
        else:
            initial_login = GUI_NO_BROWSER_LABEL
        self.browser_var = tk.StringVar(value=initial_login)
        self.status_var = tk.StringVar(value="Bereit")
        self.progress_var = tk.DoubleVar(value=0)
        self.queued_urls: list[str] = []
        self.url_listbox: tk.Listbox | None = None
        self.log_text: tk.Text | None = None
        self.pending_log_messages: list[str] = []
        self.content_frame: ttk.Frame | None = None
        self.footer_frame: ttk.Frame | None = None
        self.primary_action_button: tk.Button | None = None
        self.cancel_button: tk.Button | None = None
        self.login_button: tk.Button | None = None

        self._build_ui()
        self.after(100, self._poll_messages)

        if yt_dlp is None:
            self._set_idle_error("yt-dlp ist nicht installiert. Bitte `pip install -r requirements.txt` ausführen.")

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
        root.rowconfigure(1, weight=1)

        title = ttk.Label(root, text=APP_TITLE, style="Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        self.content_frame = ttk.Frame(root, style="App.TFrame")
        self.content_frame.grid(row=1, column=0, sticky="nsew", pady=(18, 12))
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)

        self.progress = ttk.Progressbar(root, variable=self.progress_var, maximum=100)
        self.progress.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.progress.grid_remove()

        status_row = ttk.Frame(root, style="App.TFrame")
        status_row.grid(row=3, column=0, sticky="ew")
        status_row.columnconfigure(0, weight=1)
        ttk.Label(status_row, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        self.footer_frame = ttk.Frame(status_row, style="App.TFrame")
        self.footer_frame.grid(row=0, column=1, sticky="e")

        self._show_links_step()

    def _clear_content(self) -> None:
        if self.content_frame is not None:
            for child in self.content_frame.winfo_children():
                child.destroy()
        self.url_listbox = None
        self.log_text = None
        if self.footer_frame is not None:
            for child in self.footer_frame.winfo_children():
                child.destroy()

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Any,
        *,
        variant: str = "secondary",
    ) -> tk.Button:
        colors = {
            "primary": (PRIMARY_COLOR, PRIMARY_HOVER_COLOR, "#ffffff"),
            "danger": ("#dc2626", "#b91c1c", "#ffffff"),
            "secondary": (SECONDARY_COLOR, SECONDARY_HOVER_COLOR, TEXT_COLOR),
        }
        background, active_background, foreground = colors[variant]
        return tk.Button(
            parent,
            text=text,
            command=command,
            background=background,
            activebackground=active_background,
            foreground=foreground,
            activeforeground=foreground,
            disabledforeground="#dbe4ef" if variant != "secondary" else "#94a3b8",
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            font=("TkDefaultFont", 10, "bold"),
            padx=18,
            pady=9,
            highlightthickness=0,
        )

    def _show_links_step(self) -> None:
        self._clear_content()
        self.progress.grid_remove()
        self.status_var.set("Links einfügen")
        if self.content_frame is None or self.footer_frame is None:
            return

        link_panel = ttk.Frame(self.content_frame, style="App.TFrame")
        link_panel.grid(row=0, column=0, sticky="nsew")
        link_panel.columnconfigure(0, weight=1)
        link_panel.rowconfigure(2, weight=1)

        ttk.Label(link_panel, text="Links", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        url_frame = ttk.Frame(link_panel, style="App.TFrame")
        url_frame.grid(row=1, column=0, sticky="ew", pady=(14, 10))
        url_frame.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda _event: self._add_url())
        self._button(url_frame, "Hinzufügen", self._add_url).grid(row=0, column=1, sticky="ew", padx=(10, 0))

        queue_frame = ttk.Frame(link_panel, style="App.TFrame")
        queue_frame.grid(row=2, column=0, sticky="nsew")
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)

        self.url_listbox = self._create_listbox(queue_frame, height=10)
        self.url_listbox.grid(row=0, column=0, sticky="nsew")
        self.url_listbox.bind("<Delete>", lambda _event: self._remove_selected_urls())
        queue_scrollbar = ttk.Scrollbar(queue_frame, command=self.url_listbox.yview)
        queue_scrollbar.grid(row=0, column=1, sticky="ns")
        self.url_listbox.configure(yscrollcommand=queue_scrollbar.set)
        self._sync_url_listbox()

        self.primary_action_button = self._button(
            self.footer_frame,
            "Weiter",
            self._show_options_step,
            variant="primary",
        )
        self.primary_action_button.grid(row=0, column=0, sticky="e")

    def _show_options_step(self) -> None:
        if self.url_entry.get().strip():
            self._add_url()
        if not self.queued_urls:
            messagebox.showwarning(APP_TITLE, "Bitte mindestens einen Video-Link einfügen.")
            return

        self._clear_content()
        self.progress.grid_remove()
        link_count = len(self.queued_urls)
        self.status_var.set("1 Link bereit" if link_count == 1 else f"{link_count} Links bereit")
        if self.content_frame is None or self.footer_frame is None:
            return

        options = ttk.Frame(self.content_frame, padding=16, style="Surface.TFrame")
        options.grid(row=0, column=0, sticky="nsew")
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Download einstellen", style="Surface.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 14)
        )

        ttk.Label(options, text="Qualität", style="Surface.TLabel").grid(row=1, column=0, sticky="w")
        quality_box = ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=GUI_QUALITY_CHOICES,
            state="readonly",
            width=22,
        )
        quality_box.grid(row=1, column=1, sticky="ew", padx=(10, 0))

        ttk.Label(options, text="Ordner", style="Surface.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(options, textvariable=self.folder_var).grid(
            row=2, column=1, sticky="ew", padx=(10, 10), pady=(12, 0)
        )
        self._button(options, "Wählen", self._choose_folder).grid(row=2, column=2, pady=(12, 0))
        self._button(options, "Öffnen", self._open_folder).grid(row=2, column=3, padx=(8, 0), pady=(12, 0))

        ttk.Label(options, text="Browser-Login", style="Surface.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 0))
        browser_box = ttk.Combobox(
            options,
            textvariable=self.browser_var,
            values=GUI_BROWSER_CHOICES,
            state="readonly",
            width=22,
        )
        browser_box.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(12, 0))
        self.login_button = self._button(options, "Einloggen…", self._start_login)
        self.login_button.grid(row=3, column=2, columnspan=2, sticky="w", padx=(10, 0), pady=(12, 0))
        ttk.Label(
            options,
            text=(
                "Für Seiten mit Login (z. B. Kurse): einmal auf „Einloggen…“ klicken, im Fenster "
                "einloggen und es schließen. Danach wird der Login automatisch verwendet."
            ),
            style="Surface.TLabel",
            foreground=MUTED_TEXT_COLOR,
            wraplength=460,
        ).grid(row=4, column=1, columnspan=3, sticky="w", padx=(10, 0), pady=(4, 0))

        self._button(self.footer_frame, "Zurück", self._show_links_step).grid(row=0, column=0, sticky="e", padx=(0, 8))
        self.primary_action_button = self._button(
            self.footer_frame,
            "OK",
            self._start_download,
            variant="primary",
        )
        self.primary_action_button.grid(row=0, column=1, sticky="e")

    def _show_log_step(self) -> None:
        self._clear_content()
        self.progress.grid()
        if self.content_frame is None or self.footer_frame is None:
            return

        log_frame = ttk.Frame(self.content_frame, style="App.TFrame")
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=16,
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
        for message in self.pending_log_messages:
            self._write_log(message)
        self.pending_log_messages.clear()

        self.cancel_button = self._button(self.footer_frame, "Abbrechen", self._cancel_download, variant="danger")
        self.cancel_button.grid(row=0, column=0, sticky="e")

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
        existing = set(self.queued_urls)
        added = 0
        for url in urls:
            if url in existing:
                continue
            self.queued_urls.append(url)
            existing.add(url)
            added += 1
        self._sync_url_listbox()
        if added:
            label = "Link" if added == 1 else "Links"
            self._log(f"{added} {label} zur Warteschlange hinzugefügt.")
        else:
            self._log("Keine neuen Links hinzugefügt.")

    def _remove_selected_urls(self) -> None:
        if self.url_listbox is None:
            return
        selected = list(self.url_listbox.curselection())
        if not selected:
            return
        for index in reversed(selected):
            del self.queued_urls[index]
        self._sync_url_listbox()
        self._log(f"{len(selected)} Link(s) aus der Warteschlange entfernt.")

    def _sync_url_listbox(self) -> None:
        if self.url_listbox is None:
            return
        self.url_listbox.delete(0, "end")
        for url in self.queued_urls:
            self.url_listbox.insert("end", url)

    def _reset_for_new_download(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            return
        self.queued_urls.clear()
        self.progress_var.set(0)
        self.pending_log_messages.clear()
        self.log_text = None
        self._show_links_step()

    def _finish_download_controls(self) -> None:
        if self.cancel_button is not None:
            self.cancel_button.configure(state="disabled")
        if self.footer_frame is not None:
            self._button(self.footer_frame, "Neuer Download", self._reset_for_new_download, variant="primary").grid(
                row=0, column=1, sticky="e", padx=(8, 0)
            )

    def _read_urls(self) -> list[str]:
        return [url.strip() for url in self.queued_urls if url.strip()]

    def _refresh_history(self) -> None:
        self.history_entries = load_history()

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
            messagebox.showerror(APP_TITLE, f"Ordner kann nicht geöffnet werden:\n{exc}")

    def _start_download(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            return

        try:
            pending_text = self.url_entry.get().strip() if self.url_entry.winfo_exists() else ""
        except tk.TclError:
            pending_text = ""
        if pending_text:
            self._add_urls_from_text(pending_text)
            self.url_entry.delete(0, "end")

        urls = self._read_urls()
        folder = Path(self.folder_var.get()).expanduser()
        quality = GUI_QUALITY_BY_LABEL.get(self.quality_var.get(), GUI_QUALITY_KEYS[0])
        browser = GUI_BROWSER_BY_LABEL.get(self.browser_var.get())
        use_clipboard = self.browser_var.get() == GUI_CLIPBOARD_LABEL

        if yt_dlp is None:
            messagebox.showerror(APP_TITLE, "yt-dlp ist nicht installiert.")
            return
        if not urls:
            messagebox.showwarning(APP_TITLE, "Bitte mindestens einen Video-Link einfügen.")
            return
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Download-Ordner kann nicht erstellt werden:\n{exc}")
            return

        self.settings["download_dir"] = str(folder)
        self.settings["use_download_archive"] = False
        clipboard_cookies: str | None = None
        if use_clipboard:
            try:
                clipboard_text = self.clipboard_get()
            except tk.TclError:
                clipboard_text = ""
            try:
                clipboard_cookies, _count = cookies_text_to_netscape(clipboard_text, urls[0])
            except CookieInputError as exc:
                messagebox.showwarning(APP_TITLE, str(exc))
                return
            self.clipboard_clear()
            self.clipboard_append("")

        self.settings["cookies_from_browser"] = browser
        self.settings["cookies_from_clipboard"] = use_clipboard
        save_settings(self.settings)
        self.cancel_requested.clear()
        self.progress_var.set(0)
        self.status_var.set("Download läuft...")
        self.pending_log_messages.clear()
        self._show_log_step()
        if len(urls) == 1:
            self._log(f"Starte Download: {urls[0]}")
        else:
            self._log(f"Starte Batch-Download mit {len(urls)} Links.")
        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(urls, folder, quality, browser, clipboard_cookies),
            daemon=True,
        )
        self.download_thread.start()

    def _ask_from_worker(self, question: str) -> bool:
        """Ask a yes/no question on the GUI thread and wait for the answer."""
        answered = threading.Event()
        answer = [False]
        self.messages.put(("ask_yes_no", (question, answered, answer)))
        answered.wait()
        return answer[0]

    def _start_login(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            return
        url = self.queued_urls[0] if self.queued_urls else ""
        if not url:
            messagebox.showwarning(APP_TITLE, "Bitte zuerst einen Link einfügen.")
            return
        self.login_button.configure(state="disabled")
        self.status_var.set("Browserfenster offen: einloggen und Fenster schließen...")

        def worker() -> None:
            try:
                count = interactive_login(url, login_profile_dir(), log=lambda _text: None)
            except BrowserLoginError as exc:
                self.messages.put(("login_done", f"Login nicht möglich: {exc}"))
                return
            except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
                self.messages.put(("login_done", f"Login fehlgeschlagen: {exc}"))
                return
            if count:
                self.messages.put(("login_done", f"Login gespeichert ({count} Cookies)."))
            else:
                self.messages.put(("login_done", "Keine Cookies gespeichert – warst du eingeloggt?"))

        threading.Thread(target=worker, daemon=True).start()

    def _cancel_download(self) -> None:
        if not self.download_thread or not self.download_thread.is_alive():
            return
        if self.cancel_requested.is_set():
            return
        self.cancel_requested.set()
        if self.cancel_button is not None:
            self.cancel_button.configure(state="disabled")
        self.status_var.set("Abbruch wird vorbereitet...")
        self._log("Abbruch angefordert. Der aktuelle Download wird gestoppt.")

    def _download_worker(
        self,
        urls: list[str],
        folder: Path,
        quality_key: str,
        cookies_from_browser: str | None = None,
        clipboard_cookies: str | None = None,
    ) -> None:
        if clipboard_cookies is not None:
            self.messages.put(("log", "Cookies aus der Zwischenablage werden nur temporär verwendet."))
            with temporary_cookie_file(clipboard_cookies) as cookie_file:
                self._run_downloads(urls, folder, quality_key, None, str(cookie_file))
            return
        self._run_downloads(urls, folder, quality_key, cookies_from_browser, None)

    def _run_downloads(
        self,
        urls: list[str],
        folder: Path,
        quality_key: str,
        cookies_from_browser: str | None,
        cookie_file: str | None,
    ) -> None:
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
                self.messages.put(("status", f"Lädt herunter... {speed} ETA {eta}".strip()))
            elif status == "finished":
                self.messages.put(("progress", 100))
                self.messages.put(("status", "Verarbeite Datei..."))
                filename = data.get("filename")
                if filename:
                    self.messages.put(("log", f"Heruntergeladen: {filename}"))

        def options_for(url_cookie_file: str | None) -> dict[str, Any]:
            return build_ydl_options(
                quality_key,
                folder,
                allow_playlist=False,
                cookies_from_browser=cookies_from_browser,
                cookie_file=url_cookie_file,
                use_download_archive=False,
                progress_hooks=[hook],
                logger=QueueLogger(self.messages),
            )

        def log(text: str) -> None:
            self.messages.put(("log", text))

        failures: list[str] = []
        for index, url in enumerate(urls, start=1):
            if self.cancel_requested.is_set():
                self.messages.put(("cancelled", "Download abgebrochen."))
                return
            if len(urls) > 1:
                self.messages.put(("log", f"[{index}/{len(urls)}] {url}"))
                self.messages.put(("status", f"Download {index} von {len(urls)} läuft..."))
            try:
                use_saved_login = cookie_file is None and cookies_from_browser is None

                def attempt(url: str = url, use_saved_login: bool = use_saved_login) -> Any:
                    saved = saved_login_cookie_text(url, log=log) if use_saved_login else None
                    if saved:
                        with temporary_cookie_file(saved) as saved_file:
                            return download_url(url, options_for(str(saved_file)), log=log)
                    return download_url(url, options_for(cookie_file), log=log)

                try:
                    info = attempt()
                except DownloadCancelled:
                    raise
                except Exception as first_error:  # noqa: BLE001 - maybe a login helps
                    if not (use_saved_login and login_might_help(str(first_error))):
                        raise
                    log(f"Fehler: {friendly_error(str(first_error))}")
                    site = site_of(url)
                    already = bool(saved_cookies_for(url, login_profile_dir()))
                    question = (
                        f"Der gespeicherte Login für {site} ist vielleicht abgelaufen.\n\nNeu einloggen und erneut versuchen?"
                        if already
                        else f"Vielleicht braucht {site} einen Login.\n\n"
                        "Jetzt im Browserfenster einloggen (danach Fenster schließen) und erneut versuchen?"
                    )
                    if not self._ask_from_worker(question):
                        raise
                    self.messages.put(("status", "Browserfenster offen: einloggen und Fenster schließen..."))
                    if not interactive_login(url, login_profile_dir(), log=log):
                        raise
                    log(f"Login für {site} gespeichert. Neuer Versuch...")
                    info = attempt()
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
            elif message_type == "ask_yes_no":
                question, answered, answer = payload
                try:
                    answer[0] = messagebox.askyesno(APP_TITLE, question)
                finally:
                    answered.set()
            elif message_type == "login_done":
                self.status_var.set(str(payload))
                try:
                    self.login_button.configure(state="normal")
                except (AttributeError, tk.TclError):
                    pass
                messagebox.showinfo(APP_TITLE, str(payload))
            elif message_type == "history_changed":
                self._refresh_history()
            elif message_type == "done":
                self._log(str(payload))
                self.status_var.set("Fertig")
                self._finish_download_controls()
            elif message_type == "cancelled":
                self._log(str(payload))
                self.status_var.set("Abgebrochen")
                self._finish_download_controls()
            elif message_type == "batch_error":
                self._log(f"Fehler: {payload}")
                self.status_var.set("Fertig mit Fehlern")
                self._finish_download_controls()
                messagebox.showerror(APP_TITLE, str(payload))
            elif message_type == "error":
                self._set_idle_error(str(payload))

        self.after(100, self._poll_messages)

    def _set_idle_error(self, message: str) -> None:
        self._log(f"Fehler: {message}")
        self.status_var.set("Fehler")
        if self.cancel_button is not None:
            self.cancel_button.configure(state="disabled")
        messagebox.showerror(APP_TITLE, message)

    def _log(self, message: str) -> None:
        if self.log_text is None:
            self.pending_log_messages.append(message)
            self.status_var.set(message)
            return
        self._write_log(message)

    def _write_log(self, message: str) -> None:
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
