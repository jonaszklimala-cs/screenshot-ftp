#!/usr/bin/env python3
"""
Tryb menu bar dla screenshot-ftp.

Ikona w pasku menu macOS:
  - wskaznik stanu (nasluchiwanie / przetwarzanie),
  - lista ostatnich uploadow (klik = kopiuj URL do schowka, ponownie),
  - przelaczniki: kopiowanie do schowka, otwieranie w przegladarce, pauza,
  - otworz folder / plik logu.

Wymaga: rumps  (zainstalowany w .venv)
Uruchom:  .venv/bin/python menubar.py [config.json]
"""

from __future__ import annotations  # adnotacje leniwe -> zgodnosc z Pythonem 3.9

import threading
import subprocess

import rumps
import yaml

import watcher as core


class ScreenshotFTPApp(rumps.App):
    MAX_RECENT = 10

    def __init__(self, cfg_path: str, open_settings_on_start: bool = False):
        super().__init__("SS→FTP", quit_button=None)
        self.cfg_path = cfg_path
        self.recent: list[tuple[str, str]] = []  # (nazwa, url)
        self._paused = False

        # Buduj konfiguracje + watcher z callbackiem do UI
        self.cfg, self.log, self.watcher = core.build(
            cfg_path, on_upload=self._on_upload)

        # Elementy menu
        self.status_item = rumps.MenuItem("● Nasłuchiwanie…")
        self.status_item.set_callback(None)  # nieklikalny

        self.toggle_clip = rumps.MenuItem(
            "Kopiuj URL do schowka", callback=self._toggle_clip)
        self.toggle_clip.state = bool(self.cfg.get("copy_url_to_clipboard", True))

        self.toggle_browser = rumps.MenuItem(
            "Otwieraj w przeglądarce", callback=self._toggle_browser)
        self.toggle_browser.state = bool(self.cfg.get("open_in_browser", True))

        self.pause_item = rumps.MenuItem("Wstrzymaj", callback=self._toggle_pause)

        # Naglowek + stale sloty na ostatnie zrzuty (aktualizowane w miejscu).
        # Unikalne poczatkowe tytuly, by nie kolidowaly klucze menu.
        self.recent_header = rumps.MenuItem("Ostatnie zrzuty: (brak)")
        self.recent_header.set_callback(None)
        self.recent_items: list[rumps.MenuItem] = []
        self.recent_urls: list[str | None] = [None] * self.MAX_RECENT
        for i in range(self.MAX_RECENT):
            it = rumps.MenuItem(f"__slot{i}", callback=self._make_copy_cb(i))
            it._menuitem.setHidden_(True)  # ukryty dopoki pusty
            self.recent_items.append(it)

        self.menu = [
            self.status_item,
            None,
            self.recent_header,
            *self.recent_items,
            None,
            self.toggle_clip,
            self.toggle_browser,
            self.pause_item,
            None,
            rumps.MenuItem("Ustawienia…", callback=self._open_settings),
            rumps.MenuItem("Ustaw hasło FTP…", callback=self._set_ftp_password),
            rumps.MenuItem("Otwórz folder", callback=self._open_folder),
            rumps.MenuItem("Otwórz log", callback=self._open_log),
            None,
            rumps.MenuItem("Zakończ", callback=self._quit),
        ]

        # Start watchera w tle
        self._start_watcher()

        # Pierwsze uruchomienie / niekompletna konfiguracja -> otworz Ustawienia.
        if open_settings_on_start:
            t = rumps.Timer(self._settings_on_start, 0.6)
            t.start()

    def _settings_on_start(self, timer) -> None:
        timer.stop()
        rumps.alert(
            "Witaj w screenshot-ftp",
            "Aby zacząć, uzupełnij dane serwera FTP oraz publiczny adres URL.")
        self._open_settings(None)

    # ---- watcher ----
    def _start_watcher(self) -> None:
        """(Ponownie) uruchamia watcher w watku tla dla biezacej self.cfg."""
        self.watcher = core.Watcher(self.cfg, self.log, on_upload=self._on_upload)
        self._thread = threading.Thread(target=self._run_watcher, daemon=True)
        self._thread.start()

    def _run_watcher(self) -> None:
        try:
            self.watcher.run()
        except SystemExit:
            self.status_item.title = "⚠︎ Błąd startu (sprawdź log/folder)"
        except Exception as e:  # noqa
            self.log.log(f"BLAD watchera: {e}")
            self.status_item.title = "⚠︎ Błąd (sprawdź log)"

    def _on_upload(self, url: str, path: str) -> None:
        import os
        name = os.path.basename(path)
        self.recent.insert(0, (name, url))
        self.recent = self.recent[: self.MAX_RECENT]
        self._refresh_recent()
        # migniecie statusu
        self.status_item.title = f"✓ Wysłano: {name}"
        rumps.Timer(self._reset_status, 3).start()

    def _reset_status(self, timer) -> None:
        timer.stop()
        if not self._paused:
            self.status_item.title = "● Nasłuchiwanie…"

    def _refresh_recent(self) -> None:
        """Aktualizuje stale sloty w miejscu (bez wstawiania/usuwania pozycji)."""
        self.recent_header.title = (
            "Ostatnie zrzuty:" if self.recent else "Ostatnie zrzuty: (brak)")
        for i, item in enumerate(self.recent_items):
            if i < len(self.recent):
                name, url = self.recent[i]
                item.title = f"   {name}"
                self.recent_urls[i] = url
                item._menuitem.setHidden_(False)
            else:
                self.recent_urls[i] = None
                item._menuitem.setHidden_(True)

    def _make_copy_cb(self, index: int):
        def cb(_sender):
            url = self.recent_urls[index]
            if not url:
                return
            core.copy_to_clipboard(url)
            rumps.notification("screenshot-ftp", "Skopiowano URL", url)
        return cb

    # ---- przelaczniki ----
    def _toggle_clip(self, sender) -> None:
        sender.state = not sender.state
        self.cfg["copy_url_to_clipboard"] = bool(sender.state)

    def _toggle_browser(self, sender) -> None:
        sender.state = not sender.state
        self.cfg["open_in_browser"] = bool(sender.state)

    def _toggle_pause(self, sender) -> None:
        self._paused = not self._paused
        if self._paused:
            self.watcher.stop()
            sender.title = "Wznów"
            self.status_item.title = "⏸ Wstrzymano"
        else:
            self._start_watcher()  # restart watchera
            sender.title = "Wstrzymaj"
            self.status_item.title = "● Nasłuchiwanie…"

    # ---- ustawienia ----
    def _open_settings(self, _sender, prefill: str | None = None) -> None:
        """Okno edycji config.yaml (pełny YAML), z walidacją i zastosowaniem na żywo."""
        if prefill is None:
            # pokaz aktualna konfiguracje (z pamieci -> zawsze poprawny YAML)
            prefill = yaml.safe_dump(self.cfg, sort_keys=False, allow_unicode=True,
                                     default_flow_style=False)

        win = rumps.Window(
            title="Ustawienia screenshot-ftp",
            message="Edytuj konfigurację (YAML). Zmiany zapisują się do config.yaml "
                    "i są stosowane od razu.",
            default_text=prefill,
            ok="Zapisz",
            cancel="Anuluj",
            dimensions=(480, 340),  # duze pole = edytor wieloliniowy
        )
        resp = win.run()
        if not resp.clicked:  # Anuluj / zamkniecie
            return

        text = resp.text
        # 1) parsowanie YAML
        try:
            new_cfg = yaml.safe_load(text)
        except yaml.YAMLError as e:
            rumps.alert("Błąd YAML",
                        f"Nie udało się sparsować: {e}\n\nPopraw i zapisz ponownie.")
            self._open_settings(_sender, prefill=text)  # nie gub wpisanego tekstu
            return
        if not isinstance(new_cfg, dict):
            rumps.alert("Błąd YAML",
                        "Konfiguracja musi być mapą (klucz: wartość).")
            self._open_settings(_sender, prefill=text)
            return

        # 2) walidacja pol
        errors = core.validate_config(new_cfg)
        if errors:
            rumps.alert("Niepoprawna konfiguracja", "\n".join(f"• {e}" for e in errors))
            self._open_settings(_sender, prefill=text)
            return

        # 3) zapis do pliku
        try:
            core.save_config(self.cfg_path, new_cfg)
        except OSError as e:
            rumps.alert("Błąd zapisu", f"Nie udało się zapisać {self.cfg_path}:\n{e}")
            return

        # 4) zastosuj na zywo
        self.cfg = new_cfg
        # jesli zmienil sie plik logu -> nowy Logger
        self.log = core.Logger(self.cfg.get("log_file"))
        self.toggle_clip.state = bool(self.cfg.get("copy_url_to_clipboard", True))
        self.toggle_browser.state = bool(self.cfg.get("open_in_browser", True))
        self.log.log("Zaktualizowano konfigurację z okna Ustawienia.")

        # restart watchera, by zlapal nowy folder/FTP/interwal (o ile nie wstrzymany)
        if not self._paused:
            self.watcher.stop()
            self._start_watcher()
        rumps.notification("screenshot-ftp", "Zapisano ustawienia",
                           "Konfiguracja zaktualizowana.")

        # Jesli haslo nie jest jeszcze w Keychain -> popros o nie od razu.
        if core.resolve_password(self.cfg) is None:
            self._set_ftp_password(None)

    def _set_ftp_password(self, _sender) -> None:
        """Okno z bezpiecznym polem hasla -> zapis do Keychain."""
        ftp = self.cfg.get("ftp", {})
        win = rumps.Window(
            title="Hasło FTP",
            message=f"Konto: {core._keychain_account(ftp)}\n"
                    "Hasło zostanie zapisane w Keychain (nie w pliku config.yaml).",
            ok="Zapisz",
            cancel="Anuluj",
            secure=True,                 # pole hasla (kropki)
            dimensions=(300, 24),
        )
        resp = win.run()
        if not resp.clicked:
            return
        pw = resp.text
        if not pw:
            rumps.alert("Puste hasło", "Nie zapisano — hasło było puste.")
            return
        if core.keychain_set_password(ftp, pw):
            rumps.notification("screenshot-ftp", "Zapisano hasło",
                               "Hasło FTP zapisane w Keychain.")
            self.log.log("Zapisano hasło FTP w Keychain.")
            # jesli byl wstrzymany brak hasla - zrestartuj obserwacje
            if not self._paused:
                self.watcher.stop()
                self._start_watcher()
        else:
            rumps.alert("Błąd", "Nie udało się zapisać hasła w Keychain.")

    # ---- akcje ----
    def _open_folder(self, _sender) -> None:
        subprocess.run(["open", core.expand(self.cfg["watch_dir"])])

    def _open_log(self, _sender) -> None:
        lf = self.cfg.get("log_file")
        if lf:
            subprocess.run(["open", core.expand(lf)])
        else:
            rumps.alert("Brak pliku logu w konfiguracji.")

    def _quit(self, _sender) -> None:
        self.watcher.stop()
        rumps.quit_application()


if __name__ == "__main__":
    import sys

    # Sciezka configu:
    #  - jesli podano argument .yaml/.yml/.json (tryb CLI / launchd) -> uzyj go,
    #  - w przeciwnym razie (dwuklik w .app) -> katalog uzytkownika.
    if len(sys.argv) > 1 and sys.argv[1].endswith((".yaml", ".yml", ".json")):
        cfg_path = sys.argv[1]
    else:
        cfg_path = core.user_config_path()

    core.ensure_config(cfg_path)          # utworz z szablonu przy pierwszym starcie
    cfg = core.load_config(cfg_path)
    open_settings = core.needs_setup(cfg)  # niekompletne -> pokaz okno

    ScreenshotFTPApp(cfg_path, open_settings_on_start=open_settings).run()
