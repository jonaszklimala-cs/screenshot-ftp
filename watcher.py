#!/usr/bin/env python3
"""
Screenshot -> FTP -> Schowek + Przegladarka

Obserwuje wskazany folder. Gdy pojawi sie nowy plik graficzny (zrzut ekranu
zrobiony DOWOLNYM programem), po ustabilizowaniu sie rozmiaru pliku wysyla go
na serwer FTP, kopiuje publiczny URL do schowka i/lub otwiera go w przegladarce.

Ten modul (logika + tryb CLI) nie ma zewnetrznych zaleznosci - tylko biblioteka
standardowa Pythona. Tryb menu bar jest w osobnym pliku menubar.py (wymaga rumps).
"""

from __future__ import annotations  # adnotacje leniwe -> zgodnosc z Pythonem 3.9

import json
import os
import yaml
import sys
import time
import ftplib
import select
import plistlib
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def load_config(path: str) -> dict:
    """Wczytuje konfiguracje z YAML (akceptuje tez skladnie JSON - JSON to podzbior YAML)."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Konfiguracja musi być mapą (klucz: wartość).")
    return data


def save_config(path: str, cfg: dict) -> None:
    """Zapisuje konfiguracje do pliku YAML (atomowo). Uwaga: komentarze nie sa zachowywane."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True,
                       default_flow_style=False)
    os.replace(tmp, path)


APP_NAME = "screenshot-ftp"

DEFAULT_CONFIG = {
    "watch_dir": "~/Desktop",
    "extensions": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic",
                   ".tiff", ".bmp"],
    "filename_prefixes": [],
    "poll_interval_seconds": 1.0,
    "stable_checks": 2,
    "ftp": {
        "host": "ftp.example.com",
        "port": 21,
        "user": "login",
        "use_keychain": True,   # haslo w Keychain, nie w tym pliku
        "remote_dir": "/public_html/screens",
        "passive": True,
        "use_tls": False,
    },
    "public_base_url": "https://example.com/screens",
    "copy_url_to_clipboard": True,
    "open_in_browser": True,
    "rename_pattern": "shot-{timestamp}{ext}",
    "delete_local_after_upload": False,
    "log_file": "~/Library/Logs/screenshot-ftp.log",
}

# Placeholdery z szablonu - obecnosc oznacza, ze konfiguracja nie zostala uzupelniona.
_PLACEHOLDERS = {
    "host": ("", "ftp.example.com"),
    "public_base_url": ("", "https://example.com/screens"),
}


def user_config_path() -> str:
    """Sciezka do config.yaml w katalogu uzytkownika (dla wersji .app)."""
    base = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    return os.path.join(base, "config.yaml")


def ensure_config(path: str) -> bool:
    """Tworzy plik konfiguracyjny (YAML), jesli nie istnieje.

    Jesli obok jest stary config.json, migruje go do YAML.
    Zwraca True, gdy plik zostal wlasnie utworzony/zmigrowany.
    """
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # migracja ze starego formatu JSON, jesli istnieje
    legacy = os.path.join(os.path.dirname(path), "config.json")
    if os.path.exists(legacy):
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                data = json.load(f)
            save_config(path, data)
            return True
        except Exception:
            pass  # gdy migracja sie nie uda -> uzyj szablonu
    save_config(path, DEFAULT_CONFIG)
    return True


REQUIRED_KEYS = ("watch_dir", "extensions", "public_base_url", "ftp")
REQUIRED_FTP_KEYS = ("host", "user")  # haslo walidowane osobno (plik lub Keychain)


# ---- Keychain (macOS) ----
# Haslo trzymamy w Keychain zamiast w config.json. Dostep przez systowy `security`,
# ktory jest podpisany przez Apple i stabilny (nie zalezy od podpisu naszej aplikacji).

def _keychain_account(ftp: dict) -> str:
    return f"{ftp.get('user', '')}@{ftp.get('host', '')}:{ftp.get('port', 21)}"


def keychain_get_password(ftp: dict) -> str | None:
    """Odczytuje haslo z Keychain. Zwraca None, gdy brak wpisu lub blad."""
    try:
        out = subprocess.run(
            ["security", "find-generic-password",
             "-s", APP_NAME, "-a", _keychain_account(ftp), "-w"],
            capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    pw = out.stdout.rstrip("\n")
    return pw or None


def keychain_set_password(ftp: dict, password: str) -> bool:
    """Zapisuje/aktualizuje haslo w Keychain (-U nadpisuje istniejacy wpis)."""
    try:
        out = subprocess.run(
            ["security", "add-generic-password",
             "-s", APP_NAME, "-a", _keychain_account(ftp),
             "-D", "haslo FTP", "-U", "-w", password],
            capture_output=True, text=True, timeout=15)
        return out.returncode == 0
    except Exception:
        return False


def keychain_delete_password(ftp: dict) -> bool:
    try:
        out = subprocess.run(
            ["security", "delete-generic-password",
             "-s", APP_NAME, "-a", _keychain_account(ftp)],
            capture_output=True, text=True, timeout=15)
        return out.returncode == 0
    except Exception:
        return False


def uses_keychain(ftp: dict) -> bool:
    """True, gdy haslo ma pochodzic z Keychain (jawnie lub gdy brak go w pliku)."""
    if ftp.get("use_keychain"):
        return True
    return not ftp.get("password")


def resolve_password(cfg: dict) -> str | None:
    """Zwraca haslo do polaczenia: z Keychain (gdy wlaczone) lub z pliku."""
    ftp = cfg.get("ftp", {})
    if uses_keychain(ftp):
        return keychain_get_password(ftp)
    return ftp.get("password")


def validate_config(cfg: dict) -> list[str]:
    """Zwraca liste bledow (pusta = OK). Nie rzuca wyjatkow."""
    errors: list[str] = []
    if not isinstance(cfg, dict):
        return ["Konfiguracja musi być obiektem JSON ({ ... })."]
    for k in REQUIRED_KEYS:
        if k not in cfg:
            errors.append(f"Brak wymaganego pola: {k}")
    if "extensions" in cfg and not isinstance(cfg["extensions"], list):
        errors.append("Pole 'extensions' musi być listą (np. [\".png\"]).")
    ftp = cfg.get("ftp")
    if ftp is not None:
        if not isinstance(ftp, dict):
            errors.append("Pole 'ftp' musi być obiektem.")
        else:
            for k in REQUIRED_FTP_KEYS:
                if not ftp.get(k):
                    errors.append(f"Brak wymaganego pola: ftp.{k}")
            # haslo: albo w pliku, albo w Keychain
            if not uses_keychain(ftp) and not ftp.get("password"):
                errors.append("Brak hasła FTP (pole ftp.password lub Keychain).")
    return errors


def needs_setup(cfg: dict) -> bool:
    """True, gdy konfiguracja jest niekompletna lub wciaz zawiera placeholdery."""
    if validate_config(cfg):
        return True
    ftp = cfg.get("ftp", {})
    if ftp.get("host", "") in _PLACEHOLDERS["host"]:
        return True
    if cfg.get("public_base_url", "") in _PLACEHOLDERS["public_base_url"]:
        return True
    # haslo musi byc dostepne (w pliku albo w Keychain)
    if not resolve_password(cfg):
        return True
    return False


# ---- Autostart przy logowaniu (LaunchAgent) ----
AUTOSTART_LABEL = "com.local.screenshot-ftp-app"


def autostart_plist_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{AUTOSTART_LABEL}.plist")


def autostart_enabled(path: str | None = None) -> bool:
    return os.path.exists(path or autostart_plist_path())


def _autostart_plist_dict(program_args: list[str]) -> dict:
    return {
        "Label": AUTOSTART_LABEL,
        "ProgramArguments": list(program_args),
        "RunAtLoad": True,
        "ProcessType": "Interactive",
    }


def set_autostart(enabled: bool, program_args: list[str] | None = None, *,
                  path: str | None = None, run_launchctl: bool = True) -> bool:
    """Wlacza/wylacza autostart przez LaunchAgent w ~/Library/LaunchAgents.

    Przy wlaczaniu wymaga program_args (czym uruchomic aplikacje). Zwraca True,
    gdy stan pliku zgadza sie z zadaniem (blad launchctl nie jest krytyczny -
    plist i tak zadziala przy nastepnym logowaniu).
    """
    p = path or autostart_plist_path()
    if enabled:
        if not program_args:
            return False
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            plistlib.dump(_autostart_plist_dict(program_args), f)
        if run_launchctl:
            subprocess.run(["launchctl", "load", "-w", p],
                           capture_output=True)
        return os.path.exists(p)
    else:
        if os.path.exists(p):
            if run_launchctl:
                subprocess.run(["launchctl", "unload", "-w", p],
                               capture_output=True)
            os.remove(p)
        return not os.path.exists(p)


class Logger:
    def __init__(self, log_file: str | None):
        self.fh = None
        if log_file:
            lf = expand(log_file)
            Path(lf).parent.mkdir(parents=True, exist_ok=True)
            self.fh = open(lf, "a", encoding="utf-8", buffering=1)

    def log(self, msg: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        print(line, flush=True)
        if self.fh:
            self.fh.write(line + "\n")


def copy_to_clipboard(text: str) -> bool:
    """Kopiuje tekst do schowka macOS przez pbcopy. Zwraca True przy sukcesie."""
    try:
        p = subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        return p.returncode == 0
    except Exception:
        return False


def matches(name: str, cfg: dict) -> bool:
    ext = os.path.splitext(name)[1].lower()
    if ext not in [e.lower() for e in cfg["extensions"]]:
        return False
    prefixes = cfg.get("filename_prefixes") or []
    if prefixes and not any(name.startswith(p) for p in prefixes):
        return False
    return True


def wait_until_stable(path: str, checks: int, interval: float) -> bool:
    """Zwraca True gdy rozmiar pliku jest stabilny przez `checks` odczytow."""
    last = -1
    stable = 0
    for _ in range(checks * 20 + 1):  # limit bezpieczenstwa
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        if size == last and size > 0:
            stable += 1
            if stable >= checks:
                return True
        else:
            stable = 0
            last = size
        time.sleep(interval)
    return os.path.exists(path)


def remote_name(local_name: str, cfg: dict) -> str:
    ext = os.path.splitext(local_name)[1]
    pattern = cfg.get("rename_pattern") or "{name}"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return pattern.format(
        name=os.path.splitext(local_name)[0],
        ext=ext,
        timestamp=ts,
        original=local_name,
    )


def ftp_connect(cfg: dict, log: Logger, timeout: int = 30):
    f = cfg["ftp"]
    password = resolve_password(cfg)
    if not password:
        raise RuntimeError(
            "Brak hasła FTP. Ustaw je w menu „Ustaw hasło FTP…” "
            "lub przez: python watcher.py set-password")
    conn = ftplib.FTP_TLS() if f.get("use_tls") else ftplib.FTP()
    conn.connect(f["host"], int(f.get("port", 21)), timeout=timeout)
    conn.login(f["user"], password)
    if f.get("use_tls"):
        conn.prot_p()
    conn.set_pasv(bool(f.get("passive", True)))
    remote_dir = f.get("remote_dir") or "/"
    try:
        conn.cwd(remote_dir)
    except ftplib.error_perm:
        # sprobuj utworzyc sciezke katalog po katalogu
        parts = [p for p in remote_dir.split("/") if p]
        conn.cwd("/")
        for part in parts:
            try:
                conn.cwd(part)
            except ftplib.error_perm:
                conn.mkd(part)
                conn.cwd(part)
    return conn


def upload(cfg: dict, local_path: str, log: Logger) -> str | None:
    rname = remote_name(os.path.basename(local_path), cfg)
    try:
        conn = ftp_connect(cfg, log)
    except Exception as e:
        log.log(f"BLAD polaczenia FTP: {e}")
        return None
    try:
        with open(local_path, "rb") as fh:
            conn.storbinary(f"STOR {rname}", fh)
        log.log(f"Wyslano: {os.path.basename(local_path)} -> {rname}")
    except Exception as e:
        log.log(f"BLAD wysylania {local_path}: {e}")
        try:
            conn.quit()
        except Exception:
            pass
        return None
    try:
        conn.quit()
    except Exception:
        pass
    base = cfg["public_base_url"].rstrip("/")
    return f"{base}/{quote(rname)}"


class Watcher:
    """Obserwuje folder i przetwarza nowe zrzuty.

    on_upload(url, local_path) - opcjonalny callback wywolywany po udanym wysylaniu
    (np. do aktualizacji menu bar).
    """

    def __init__(self, cfg: dict, log: Logger, on_upload=None):
        self.cfg = cfg
        self.log = log
        self.on_upload = on_upload
        self.watch_dir = expand(cfg["watch_dir"])
        self.interval = float(cfg.get("poll_interval_seconds", 1.0))
        self._stop = False
        self.seen: set[str] = set()
        self._wake_w: int | None = None  # koniec self-pipe do wybudzenia kqueue

    def stop(self) -> None:
        self._stop = True
        # wybudz watek zablokowany w kqueue (jesli dziala tryb zdarzeniowy)
        if self._wake_w is not None:
            try:
                os.write(self._wake_w, b"x")
            except OSError:
                pass

    def _process(self, path: str) -> str | None:
        cfg = self.cfg
        if not wait_until_stable(path, int(cfg.get("stable_checks", 2)),
                                 self.interval):
            self.log.log(f"Pomijam (plik zniknal/niestabilny): {path}")
            return None
        url = upload(cfg, path, self.log)
        if not url:
            return None
        self.log.log(f"URL: {url}")

        if cfg.get("copy_url_to_clipboard", True):
            if copy_to_clipboard(url):
                self.log.log("Skopiowano URL do schowka.")
            else:
                self.log.log("Nie udalo sie skopiowac do schowka (pbcopy).")

        if cfg.get("open_in_browser", True):
            webbrowser.open(url)

        if cfg.get("delete_local_after_upload", False):
            try:
                os.remove(path)
                self.log.log(f"Usunieto lokalny plik: {path}")
            except OSError as e:
                self.log.log(f"Nie udalo sie usunac {path}: {e}")

        if self.on_upload:
            try:
                self.on_upload(url, path)
            except Exception as e:
                self.log.log(f"BLAD callbacku on_upload: {e}")
        return url

    def scan_once(self) -> None:
        try:
            current = set(os.listdir(self.watch_dir))
        except OSError as e:
            self.log.log(f"Blad odczytu folderu: {e}")
            return
        new_files = current - self.seen
        for name in sorted(new_files):
            self.seen.add(name)
            if name.startswith("."):
                continue
            if not matches(name, self.cfg):
                continue
            full = os.path.join(self.watch_dir, name)
            if not os.path.isfile(full):
                continue
            self.log.log(f"Nowy zrzut: {name}")
            try:
                self._process(full)
            except Exception as e:
                self.log.log(f"BLAD przetwarzania {name}: {e}")
        # usun z 'seen' pliki ktore zniknely (by ponowny plik o tej nazwie zadzialal)
        self.seen &= current | new_files

    def run(self) -> None:
        if not os.path.isdir(self.watch_dir):
            self.log.log(f"Folder do obserwacji nie istnieje: {self.watch_dir}")
            raise SystemExit(1)
        # nie wysylaj tego, co bylo przed startem
        self.seen = set(os.listdir(self.watch_dir))
        self.log.log(f"Start. Obserwuje: {self.watch_dir}. "
                     f"Zignorowano {len(self.seen)} istniejacych plikow.")
        # Tryb zdarzeniowy (kqueue) = zero wybudzen w bezczynnosci (oszczedza baterie).
        # Gdy sie nie powiedzie (np. dysk sieciowy) -> fallback na polling.
        if not self._run_kqueue():
            self.log.log("kqueue niedostepne — tryb pollingu "
                         f"(co {self.interval}s).")
            self._run_poll()

    def _run_poll(self) -> None:
        """Zapasowy tryb: cykliczne skanowanie (jak dotychczas)."""
        while not self._stop:
            self.scan_once()
            time.sleep(self.interval)

    def _run_kqueue(self) -> bool:
        """Tryb zdarzeniowy: watek spi w jadrze do czasu realnej zmiany w folderze.

        Zwraca False, gdy nie udalo sie zainicjowac (wtedy wywolujacy robi fallback).
        """
        open_flags = getattr(os, "O_EVTONLY", os.O_RDONLY)
        try:
            dir_fd = os.open(self.watch_dir, open_flags)
        except OSError as e:
            self.log.log(f"kqueue: nie moge otworzyc folderu: {e}")
            return False

        wake_r, wake_w = os.pipe()
        self._wake_w = wake_w
        try:
            kq = select.kqueue()
        except Exception as e:  # noqa
            self.log.log(f"kqueue: init nieudany: {e}")
            os.close(dir_fd); os.close(wake_r); os.close(wake_w)
            self._wake_w = None
            return False

        vnode_flags = (select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND
                       | select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME
                       | select.KQ_NOTE_ATTRIB)
        vnode_ev = select.kevent(
            dir_fd, filter=select.KQ_FILTER_VNODE,
            flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR, fflags=vnode_flags)
        pipe_ev = select.kevent(
            wake_r, filter=select.KQ_FILTER_READ, flags=select.KQ_EV_ADD)

        try:
            kq.control([vnode_ev, pipe_ev], 0, 0)  # rejestracja, bez czekania
            # jednorazowy skan na wypadek pliku dodanego tuz po seed
            self.scan_once()
            while not self._stop:
                events = kq.control(None, 8, None)  # blokuje do zdarzenia
                if self._stop:
                    break
                reopen = False
                fs_changed = False
                for ev in events:
                    if ev.ident == dir_fd:
                        fs_changed = True
                        if ev.fflags & (select.KQ_NOTE_DELETE
                                        | select.KQ_NOTE_RENAME):
                            reopen = True
                    # ev.ident == wake_r -> tylko wybudzenie (stop)
                if fs_changed:
                    self.scan_once()
                if reopen:
                    # folder przeniesiony/usuniety -> sprobuj otworzyc ponownie
                    try:
                        os.close(dir_fd)
                        dir_fd = os.open(self.watch_dir, open_flags)
                        kq.control([select.kevent(
                            dir_fd, filter=select.KQ_FILTER_VNODE,
                            flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                            fflags=vnode_flags)], 0, 0)
                        self.scan_once()
                    except OSError as e:
                        self.log.log(f"kqueue: folder zniknal ({e}) — fallback.")
                        return False
        except Exception as e:  # noqa
            self.log.log(f"kqueue: blad petli ({e}) — fallback na polling.")
            return False
        finally:
            for fd in (dir_fd, wake_r, wake_w):
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._wake_w = None
            try:
                kq.close()
            except Exception:
                pass
        return True


def resolve_config_path() -> str:
    return sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml")


def build(cfg_path: str, on_upload=None) -> tuple[dict, Logger, Watcher]:
    if not os.path.exists(cfg_path):
        print(f"Brak pliku konfiguracyjnego: {cfg_path}", file=sys.stderr)
        print("Skopiuj config.example.yaml do config.yaml i uzupelnij dane.",
              file=sys.stderr)
        raise SystemExit(1)
    cfg = load_config(cfg_path)
    log = Logger(cfg.get("log_file"))
    return cfg, log, Watcher(cfg, log, on_upload=on_upload)


def cmd_set_password(argv: list[str]) -> None:
    """Ustawia haslo FTP w Keychain. Uzycie: watcher.py set-password [config.yaml]"""
    import getpass
    cfg_path = argv[0] if argv else resolve_config_path()
    if not os.path.exists(cfg_path):
        cfg_path = user_config_path()
    if not os.path.exists(cfg_path):
        print(f"Brak pliku konfiguracyjnego: {cfg_path}", file=sys.stderr)
        raise SystemExit(1)
    cfg = load_config(cfg_path)
    ftp = cfg.get("ftp", {})
    print(f"Konto FTP: {_keychain_account(ftp)}")
    pw = getpass.getpass("Hasło FTP (wpisz, nie będzie widoczne): ")
    if not pw:
        print("Anulowano (puste hasło).", file=sys.stderr)
        raise SystemExit(1)
    if keychain_set_password(ftp, pw):
        print("Zapisano hasło w Keychain.")
    else:
        print("Nie udało się zapisać do Keychain.", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "set-password":
        cmd_set_password(argv[1:])
        return
    _, _, watcher = build(resolve_config_path())
    watcher.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nZatrzymano.")
