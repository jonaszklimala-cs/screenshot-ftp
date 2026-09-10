"""Screenshot -> FTP (Windows) — ikona w zasobniku (tray).

Obserwuje folder (watchdog), wysyła nowe zrzuty na FTP, kopiuje URL do schowka
(pyperclip) i otwiera w przeglądarce. Hasło z Windows Credential Manager (keyring).
Ustawienia przez formularz Tkinter. Autostart przez rejestr.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser

import pyperclip
import pystray
from pystray import MenuItem as Item, Menu
from PIL import Image, ImageDraw
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import watcher as core  # noqa: E402
import paths_win  # noqa: E402
import secrets_win  # noqa: E402
import settings_win  # noqa: E402

import tkinter as tk  # noqa: E402


def _icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, 58, 58], radius=12, fill=(30, 120, 220, 255))
    d.text((23, 20), "S", fill=(255, 255, 255, 255))
    return img


def win_needs_setup(cfg: dict) -> bool:
    ftp = cfg.get("ftp", {}) or {}
    if not ftp.get("host") or ftp.get("host") == "ftp.example.com":
        return True
    if not ftp.get("user"):
        return True
    if (cfg.get("public_base_url", "") in ("", "https://example.com/screens")):
        return True
    if secrets_win.get_password(ftp) is None:
        return True
    return False


class _Handler(FileSystemEventHandler):
    def __init__(self, app):
        self.app = app

    def on_created(self, event):
        if not event.is_directory:
            self.app.handle_new(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.app.handle_new(event.dest_path)


class WinApp:
    def __init__(self, cfg: dict, cfg_path: str):
        self.cfg = cfg
        self.cfg_path = cfg_path
        self.log = core.Logger(cfg.get("log_file"))
        self.copy_clip = bool(cfg.get("copy_url_to_clipboard", True))
        self.open_browser = bool(cfg.get("open_in_browser", True))
        self.paused = False
        self.last_url: str | None = None
        self._processed: set[str] = set()
        self.observer: Observer | None = None
        self.icon: pystray.Icon | None = None
        self.root: tk.Tk | None = None
        self._settings_open = False

    # ---- obserwacja ----
    def start_observer(self):
        watch = os.path.expanduser(os.path.expandvars(self.cfg["watch_dir"]))
        try:
            os.makedirs(watch, exist_ok=True)
        except OSError:
            pass
        if not os.path.isdir(watch):
            self.log.log(f"Folder do obserwacji nie istnieje: {watch}")
            return
        obs = Observer()
        obs.schedule(_Handler(self), watch, recursive=False)
        obs.start()
        self.observer = obs
        self.log.log(f"Start. Obserwuje: {watch}")

    def stop_observer(self):
        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=3)
            except Exception:
                pass
            self.observer = None

    def handle_new(self, path: str):
        if self.paused:
            return
        name = os.path.basename(path)
        if name.startswith(".") or not core.matches(name, self.cfg):
            return
        if path in self._processed:
            return
        self._processed.add(path)
        if not core.wait_until_stable(
                path, int(self.cfg.get("stable_checks", 2)),
                float(self.cfg.get("poll_interval_seconds", 1.0))):
            return
        self.log.log(f"Nowy zrzut: {name}")
        pw = secrets_win.get_password(self.cfg.get("ftp", {}))
        try:
            url = core.upload(self.cfg, path, self.log, password=pw)
        except Exception as e:  # noqa
            self.log.log(f"BLAD przetwarzania {name}: {e}")
            return
        if not url:
            return
        self.last_url = url
        self.log.log(f"URL: {url}")
        if self.copy_clip:
            try:
                pyperclip.copy(url)
            except Exception as e:
                self.log.log(f"Schowek nieudany: {e}")
        if self.open_browser:
            webbrowser.open(url)
        if self.cfg.get("delete_local_after_upload", False):
            try:
                os.remove(path)
            except OSError:
                pass
        self._update_menu()

    # ---- tray menu ----
    def _build_menu(self) -> Menu:
        return Menu(
            Item("Ustawienia FTP…", self._on_settings, default=True),
            Menu.SEPARATOR,
            Item("Kopiuj ostatni URL", self._on_copy_last,
                 enabled=lambda i: self.last_url is not None),
            Item("Kopiuj URL do schowka", self._on_toggle_clip,
                 checked=lambda i: self.copy_clip),
            Item("Otwieraj w przeglądarce", self._on_toggle_browser,
                 checked=lambda i: self.open_browser),
            Item("Wstrzymaj", self._on_toggle_pause,
                 checked=lambda i: self.paused),
            Menu.SEPARATOR,
            Item("Otwórz folder", self._on_open_folder),
            Item("Zakończ", self._on_quit),
        )

    def _update_menu(self):
        if self.icon is not None:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def _on_copy_last(self, icon, item):
        if self.last_url:
            try:
                pyperclip.copy(self.last_url)
            except Exception:
                pass

    def _on_toggle_clip(self, icon, item):
        self.copy_clip = not self.copy_clip
        self._update_menu()

    def _on_toggle_browser(self, icon, item):
        self.open_browser = not self.open_browser
        self._update_menu()

    def _on_toggle_pause(self, icon, item):
        self.paused = not self.paused
        self._update_menu()

    def _on_open_folder(self, icon, item):
        watch = os.path.expanduser(os.path.expandvars(self.cfg["watch_dir"]))
        try:
            os.startfile(watch)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_settings(self, icon, item):
        # UI musi powstac w watku glownym Tk
        if self.root is not None:
            self.root.after(0, self._open_settings)

    def _on_quit(self, icon, item):
        self.stop_observer()
        try:
            icon.stop()
        except Exception:
            pass
        if self.root is not None:
            self.root.after(0, self.root.quit)

    # ---- ustawienia (watek Tk) ----
    def _open_settings(self, first_run=False):
        if self._settings_open:
            return
        self._settings_open = True
        win = settings_win.open_settings(
            self.root, self.cfg, self.cfg_path,
            on_saved=self.apply_cfg, first_run=first_run)

        def _closed():
            self._settings_open = False
        win.protocol("WM_DELETE_WINDOW", lambda: (_closed(), win.destroy()))
        win.bind("<Destroy>", lambda e: _closed() if e.widget is win else None)

    def apply_cfg(self, new_cfg: dict):
        self.cfg = new_cfg
        self.log = core.Logger(new_cfg.get("log_file"))
        self.copy_clip = bool(new_cfg.get("copy_url_to_clipboard", True))
        self.open_browser = bool(new_cfg.get("open_in_browser", True))
        self._processed.clear()
        self.stop_observer()
        if not self.paused:
            self.start_observer()
        self._update_menu()
        self.log.log("Zaktualizowano konfigurację.")

    # ---- start ----
    def run(self, open_settings_on_start=False):
        self.root = tk.Tk()
        self.root.withdraw()  # ukryte okno glowne — trzyma petle Tk
        self.start_observer()
        self.icon = pystray.Icon("screenshot-ftp", _icon_image(),
                                 "Screenshot FTP", menu=self._build_menu())
        threading.Thread(target=self.icon.run, daemon=True).start()
        if open_settings_on_start:
            self.root.after(600, lambda: self._open_settings(first_run=True))
        self.root.mainloop()


def main():
    cfg_path = paths_win.user_config_path()
    paths_win.ensure_config(cfg_path)
    cfg = core.load_config(cfg_path)
    app = WinApp(cfg, cfg_path)
    app.run(open_settings_on_start=win_needs_setup(cfg))


if __name__ == "__main__":
    main()
