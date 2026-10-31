"""Video Downloader - window version of vd (same download logic as the command line)."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from browser_login import delete_site_login, saved_sites
from i18n import LANGUAGES, set_language, t
from site_auth import Credentials, credential_sites, delete_credentials
from vd_cli import (
    QUALITY_OPTIONS,
    __version__,
    add_history_entry,
    downloaded_file,
    extract_urls_from_text,
    format_eta,
    format_size,
    friendly_error,
    load_settings,
    login_profile_dir,
    quality_label,
    run_download,
    save_settings,
)

try:
    import yt_dlp
except ImportError:  # pragma: no cover - handled in GUI startup
    yt_dlp = None

MUTED = "#6b7280"
PAD = 12


def enable_high_dpi_rendering() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


class DownloadCancelled(RuntimeError):
    pass


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        set_language(self.settings["language"])
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.download_thread: threading.Thread | None = None
        self.cancel_requested = threading.Event()

        self.folder_var = tk.StringVar(value=self.settings["download_dir"])
        self.quality_key = self.settings["quality"]
        self.quality_var = tk.StringVar()
        self.playlist_var = tk.BooleanVar(value=False)
        self.language_var = tk.StringVar(value=LANGUAGES[self.settings["language"]])
        self.status_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        self.links_text: tk.Text | None = None
        self.log_text: tk.Text | None = None

        self._set_window_icon()
        width, height = 760, 600
        x = max((self.winfo_screenwidth() - width) // 2, 0)
        y = max((self.winfo_screenheight() - height) // 3, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(620, 520)
        self._configure_style()
        self._build_ui()
        self.after(100, self._poll_messages)
        if yt_dlp is None:
            self._log(t("ytdlp_missing"))

    # ------------------------------------------------------------------ layout

    def _set_window_icon(self) -> None:
        try:
            import app_icon

            self._icon = tk.PhotoImage(data=app_icon.PNG_BASE64)
            self.iconphoto(True, self._icon)
        except Exception:  # noqa: BLE001 - cosmetic only
            pass

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if os.name == "nt" and "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold") if os.name == "nt" else ("TkDefaultFont", 15, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        bold = ("Segoe UI", 10, "bold") if os.name == "nt" else ("TkDefaultFont", 10, "bold")
        style.configure("Section.TLabel", font=bold)
        style.configure("Primary.TButton", font=bold, padding=(18, 4))

    def _build_ui(self) -> None:
        """(Re)build all widgets, e.g. after switching the language. Keeps links and log."""
        links = self.links_text.get("1.0", "end").strip() if self.links_text is not None else ""
        log = self.log_text.get("1.0", "end").strip() if self.log_text is not None else ""
        for child in self.winfo_children():
            child.destroy()

        self.title(t("gui.title"))
        root = ttk.Frame(self, padding=PAD)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=3)
        root.rowconfigure(6, weight=2)

        # Header: title, language, logins
        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew", pady=(0, PAD))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=t("gui.title"), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=t("gui.language"), style="Muted.TLabel").grid(row=0, column=1, padx=(0, 6))
        language_box = ttk.Combobox(
            header, textvariable=self.language_var, values=list(LANGUAGES.values()), state="readonly", width=9
        )
        language_box.grid(row=0, column=2)
        language_box.bind("<<ComboboxSelected>>", lambda _e: self._change_language())
        ttk.Button(header, text=t("gui.logins"), command=self._show_logins).grid(row=0, column=3, padx=(8, 0))

        # Links
        links_frame = ttk.Frame(root)
        links_frame.grid(row=1, column=0, sticky="nsew")
        links_frame.columnconfigure(0, weight=1)
        links_frame.rowconfigure(1, weight=1)
        ttk.Label(links_frame, text=t("gui.links"), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        buttons = ttk.Frame(links_frame)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text=t("gui.paste"), command=self._paste_links).pack(side="left")
        ttk.Button(buttons, text=t("gui.clear"), command=lambda: self.links_text.delete("1.0", "end")).pack(
            side="left", padx=(6, 0)
        )
        self.links_text = self._text(links_frame, height=5)
        self.links_text.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        if links:
            self.links_text.insert("1.0", links)

        # Options: quality, playlist, folder
        options = ttk.Frame(root)
        options.grid(row=2, column=0, sticky="ew", pady=(PAD, 0))
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text=t("gui.quality")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        quality_labels = [quality_label(key) for key in QUALITY_OPTIONS]
        self.quality_var.set(quality_label(self.quality_key))
        quality_box = ttk.Combobox(
            options, textvariable=self.quality_var, values=quality_labels, state="readonly", width=22
        )
        quality_box.grid(row=0, column=1, sticky="w")
        quality_box.bind("<<ComboboxSelected>>", lambda _e: self._remember_quality())
        ttk.Checkbutton(options, text=t("gui.playlist"), variable=self.playlist_var).grid(
            row=0, column=2, columnspan=2, sticky="e"
        )
        ttk.Label(options, text=t("gui.folder")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(options, textvariable=self.folder_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(options, text=t("gui.choose"), command=self._choose_folder).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0)
        )
        ttk.Button(options, text=t("gui.open"), command=self._open_folder).grid(
            row=1, column=3, padx=(6, 0), pady=(8, 0)
        )
        ttk.Label(options, text=t("gui.login_hint"), style="Muted.TLabel", wraplength=700).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        # Actions
        actions = ttk.Frame(root)
        actions.grid(row=3, column=0, sticky="ew", pady=(PAD, 0))
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(actions, text=t("gui.cancel"), command=self._cancel_download)
        self.cancel_button.grid(row=0, column=1, padx=(0, 8))
        self.download_button = ttk.Button(
            actions, text=t("gui.download"), command=self._start_download, style="Primary.TButton"
        )
        self.download_button.grid(row=0, column=2)
        ttk.Progressbar(root, variable=self.progress_var, maximum=100).grid(
            row=4, column=0, sticky="ew", pady=(8, 0)
        )

        # Activity log
        log_header = ttk.Frame(root)
        log_header.grid(row=5, column=0, sticky="ew", pady=(PAD, 0))
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text=t("gui.activity"), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(log_header, text=f"vd {__version__}", style="Muted.TLabel").grid(row=0, column=1, sticky="e")
        self.log_text = self._text(root, height=4, readonly=True)
        self.log_text.grid(row=6, column=0, sticky="nsew", pady=(6, 0))
        if log:
            self._append_log(log)

        running = bool(self.download_thread and self.download_thread.is_alive())
        self._set_running(running)
        if not running:
            self.status_var.set(t("gui.ready"))

    def _text(self, parent: tk.Misc, *, height: int, readonly: bool = False) -> tk.Text:
        text = tk.Text(
            parent, height=height, wrap="word", relief="solid", borderwidth=1, padx=8, pady=6, undo=not readonly
        )
        if readonly:
            text.configure(state="disabled", background="#f7f7f8")
        return text

    def _set_running(self, running: bool) -> None:
        self.download_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    # ------------------------------------------------------------------ settings

    def _change_language(self) -> None:
        code = next(code for code, name in LANGUAGES.items() if name == self.language_var.get())
        self.settings["language"] = code
        save_settings(self.settings)
        set_language(code)
        self._build_ui()

    def _remember_quality(self) -> None:
        labels = {quality_label(key): key for key in QUALITY_OPTIONS}
        self.quality_key = labels.get(self.quality_var.get(), self.quality_key)
        self.settings["quality"] = self.quality_key
        save_settings(self.settings)

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()), parent=self)
        if folder:
            self.folder_var.set(folder)
            self.settings["download_dir"] = folder
            save_settings(self.settings)

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
            messagebox.showerror(t("gui.title"), t("gui.open_error", error=exc), parent=self)

    def _paste_links(self) -> None:
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        if text:
            current = self.links_text.get("1.0", "end").strip()
            self.links_text.insert("end", ("\n" if current else "") + text)

    # ------------------------------------------------------------------ logins

    def _show_logins(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(t("gui.logins_title"))
        dialog.transient(self)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=PAD)
        frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(frame, height=8, width=42, relief="solid", borderwidth=1)
        empty = ttk.Label(frame, text=t("gui.logins_empty"), style="Muted.TLabel", justify="left")

        def refresh() -> None:
            profile = login_profile_dir()
            sites = sorted({site for site, _count in saved_sites(profile)} | set(credential_sites(profile)))
            listbox.delete(0, "end")
            for site in sites:
                listbox.insert("end", site)
            if sites:
                empty.grid_remove()
                listbox.grid(row=0, column=0, columnspan=2, sticky="nsew")
            else:
                listbox.grid_remove()
                empty.grid(row=0, column=0, columnspan=2, sticky="w")

        def logout() -> None:
            for index in reversed(listbox.curselection()):
                site = listbox.get(index)
                delete_site_login(login_profile_dir(), site)
                delete_credentials(login_profile_dir(), site)
            refresh()

        ttk.Button(frame, text=t("gui.logout"), command=logout).grid(row=1, column=0, sticky="w", pady=(PAD, 0))
        ttk.Button(frame, text=t("gui.close"), command=dialog.destroy).grid(row=1, column=1, sticky="e", pady=(PAD, 0))
        refresh()
        dialog.grab_set()

    # ------------------------------------------------------------------ downloading

    def _start_download(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            return
        urls = extract_urls_from_text(self.links_text.get("1.0", "end"))
        if not urls:
            messagebox.showwarning(t("gui.title"), t("gui.no_links"), parent=self)
            return
        if yt_dlp is None:
            messagebox.showerror(t("gui.title"), t("ytdlp_missing"), parent=self)
            return
        folder = Path(self.folder_var.get()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(t("gui.title"), t("gui.folder_error", error=exc), parent=self)
            return

        self._remember_quality()
        self.settings["download_dir"] = str(folder)
        save_settings(self.settings)
        self.cancel_requested.clear()
        self.progress_var.set(0)
        self.status_var.set(t("gui.running"))
        self._set_running(True)
        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(urls, folder, self.quality_key, self.playlist_var.get()),
            daemon=True,
        )
        self.download_thread.start()

    def _cancel_download(self) -> None:
        if self.download_thread and self.download_thread.is_alive() and not self.cancel_requested.is_set():
            self.cancel_requested.set()
            self.status_var.set(t("gui.cancelling"))

    def _download_worker(self, urls: list[str], folder: Path, quality_key: str, playlist: bool = False) -> None:
        def hook(data: dict[str, Any]) -> None:
            if self.cancel_requested.is_set():
                raise DownloadCancelled(t("cancelled"))
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                done = data.get("downloaded_bytes") or 0
                percent = min(done / total * 100, 100) if total else 0
                self.messages.put(("progress", percent))
                if data.get("speed") and data.get("eta") is not None:
                    self.messages.put((
                        "status",
                        t(
                            "gui.speed",
                            percent=f"{percent:.0f} %",
                            speed=f"{format_size(data['speed'])}/s",
                            eta=format_eta(data["eta"]),
                        ),
                    ))
            elif data.get("status") == "finished":
                self.messages.put(("progress", 100))
                self.messages.put(("status", t("gui.processing")))

        def log(text: str) -> None:
            self.messages.put(("log", text))

        failures = 0
        for index, url in enumerate(urls, start=1):
            if self.cancel_requested.is_set():
                break
            if len(urls) > 1:
                self.messages.put(("status", t("gui.running_n", index=index, total=len(urls))))
            log(url)
            try:
                info = run_download(
                    url,
                    quality_key,
                    folder,
                    playlist=playlist,
                    progress_hooks=[hook],
                    log=log,
                    ask=self._ask_from_worker,
                    ask_credentials=self._ask_credentials_from_worker,
                )
            except DownloadCancelled:
                break
            except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
                failures += 1
                log(t("error", message=friendly_error(str(exc))))
                continue
            title = info.get("title", "Video") if isinstance(info, dict) else "Video"
            add_history_entry(url, title=title, quality_key=quality_key, folder=folder)
            log(t("saved", path=downloaded_file(info) or title))

        if self.cancel_requested.is_set():
            self.messages.put(("finished", t("cancelled")))
        elif failures:
            self.messages.put(("finished", t("failures", failed=failures, total=len(urls))))
        else:
            self.messages.put(("finished", t("gui.done_one") if len(urls) == 1 else t("gui.done_all", total=len(urls))))

    # ------------------------------------------------------------------ questions from the download thread

    def _ask_from_worker(self, question: str) -> bool:
        answered = threading.Event()
        answer = [False]
        self.messages.put(("ask_yes_no", (question, answered, answer)))
        answered.wait()
        if answer[0]:
            self.messages.put(("status", t("gui.login_window_status")))
        return answer[0]

    def _ask_credentials_from_worker(self, site: str, wrong: bool) -> Credentials | None:
        answered = threading.Event()
        answer: list[Credentials | None] = [None]
        self.messages.put(("ask_credentials", (site, wrong, answered, answer)))
        answered.wait()
        return answer[0]

    def _show_credentials_dialog(self, site: str, wrong: bool) -> Credentials | None:
        intro = t("gui.credentials_wrong") if wrong else ""
        username = simpledialog.askstring(
            t("gui.title"), t("gui.credentials_prompt", intro=intro, site=site), parent=self
        )
        if not username:
            return None
        password = simpledialog.askstring(t("gui.title"), t("gui.password_for", user=username), show="*", parent=self)
        if password is None:
            return None
        return Credentials(username.strip(), password)

    # ------------------------------------------------------------------ message loop

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log(str(payload))
            elif kind == "progress":
                self.progress_var.set(float(payload))
            elif kind == "status":
                self.status_var.set(str(payload))
            elif kind == "ask_yes_no":
                question, answered, answer = payload
                try:
                    answer[0] = messagebox.askyesno(t("gui.title"), question, parent=self)
                finally:
                    answered.set()
            elif kind == "ask_credentials":
                site, wrong, answered, answer = payload
                try:
                    answer[0] = self._show_credentials_dialog(site, wrong)
                finally:
                    answered.set()
            elif kind == "finished":
                self._log(str(payload))
                self.status_var.set(str(payload))
                self._set_running(False)
        self.after(100, self._poll_messages)

    def _log(self, message: str) -> None:
        if self.log_text is not None:
            self._append_log(message)

    def _append_log(self, message: str) -> None:
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
