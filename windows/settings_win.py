"""Formularz ustawień FTP (Tkinter) — wersja Windows.

Pola: Host, Port, User, Password, Zdalny folder, Base URL, Obserwuj (+ przeglądaj),
Passive, TLS, Autostart. Przyciski: Testuj ustawienia / Wyczyść / Zapisz.
Hasło zapisywane w Windows Credential Manager (keyring).
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import watcher as core  # noqa: E402
import secrets_win  # noqa: E402
import autostart_win  # noqa: E402


class _NullLog:
    def log(self, *a):
        pass


def open_settings(root, cfg: dict, cfg_path: str, on_saved, first_run=False):
    ftp = dict(cfg.get("ftp", {}) or {})

    win = tk.Toplevel(root)
    win.title("Ustawienia FTP")
    win.resizable(False, False)
    frm = ttk.Frame(win, padding=14)
    frm.grid(sticky="nsew")

    row = 0

    def add_entry(label, value="", show=None, width=40):
        nonlocal row
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="e", padx=(0, 8),
                                        pady=3)
        var = tk.StringVar(value=str(value))
        ent = ttk.Entry(frm, textvariable=var, width=width, show=show)
        ent.grid(row=row, column=1, columnspan=2, sticky="we", pady=3)
        row += 1
        return var

    host_v = add_entry("Host:", ftp.get("host", ""))
    port_v = add_entry("Port:", ftp.get("port", 21), width=10)
    user_v = add_entry("User:", ftp.get("user", ""))

    has_pw = secrets_win.get_password(ftp) is not None
    pw_v = add_entry("Password:", "", show="*")
    ttk.Label(frm, text=("(zapisane — puste = bez zmian)" if has_pw
                         else "(wpisz hasło)"),
              foreground="#888").grid(row=row, column=1, sticky="w")
    row += 1

    remote_v = add_entry("Zdalny folder:", ftp.get("remote_dir", ""))
    base_v = add_entry("Base URL:", cfg.get("public_base_url", ""))

    # Obserwuj + przeglądaj
    ttk.Label(frm, text="Obserwuj:").grid(row=row, column=0, sticky="e",
                                          padx=(0, 8), pady=3)
    watch_v = tk.StringVar(value=str(cfg.get("watch_dir", "")))
    ttk.Entry(frm, textvariable=watch_v, width=30).grid(row=row, column=1,
                                                        sticky="we", pady=3)

    def browse():
        d = filedialog.askdirectory(parent=win, title="Wybierz folder")
        if d:
            watch_v.set(d)

    ttk.Button(frm, text="Przeglądaj…", command=browse).grid(row=row, column=2,
                                                             sticky="we", padx=(6, 0))
    row += 1

    passive_v = tk.BooleanVar(value=bool(ftp.get("passive", True)))
    tls_v = tk.BooleanVar(value=bool(ftp.get("use_tls", False)))
    autostart_v = tk.BooleanVar(value=autostart_win.enabled())
    ttk.Checkbutton(frm, text="Passive mode", variable=passive_v).grid(
        row=row, column=1, sticky="w")
    ttk.Checkbutton(frm, text="TLS (FTPS)", variable=tls_v).grid(
        row=row, column=2, sticky="w")
    row += 1
    ttk.Checkbutton(frm, text="Uruchamiaj przy logowaniu",
                    variable=autostart_v).grid(row=row, column=1, columnspan=2,
                                               sticky="w")
    row += 1

    status = ttk.Label(frm, text="", foreground="#666")
    status.grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def set_status(text, error=False):
        status.config(text=text, foreground=("#c00" if error else "#666"))

    def collect_ftp(with_pw_from_field=False):
        try:
            port = int(str(port_v.get()).strip() or "21")
        except ValueError:
            port = None
        f = dict(ftp)
        f["host"] = host_v.get().strip()
        if port is not None:
            f["port"] = port
        f["user"] = user_v.get().strip()
        f["remote_dir"] = remote_v.get().strip()
        f["passive"] = bool(passive_v.get())
        f["use_tls"] = bool(tls_v.get())
        f["use_keychain"] = True
        f.pop("password", None)
        if with_pw_from_field:
            pw = pw_v.get()
            if pw:
                f = dict(f, use_keychain=False, password=pw)
        return f, port

    def do_save():
        f, port = collect_ftp()
        if not f["host"] or not f["user"]:
            set_status("Host i User są wymagane.", error=True)
            return
        if port is None:
            set_status("Port musi być liczbą.", error=True)
            return
        new_cfg = dict(cfg)
        new_cfg["ftp"] = f
        new_cfg["public_base_url"] = base_v.get().strip()
        w = watch_v.get().strip()
        if w:
            new_cfg["watch_dir"] = w
        try:
            core.save_config(cfg_path, new_cfg)
        except OSError as e:
            set_status(f"Błąd zapisu: {e}", error=True)
            return
        pw = pw_v.get()
        if pw and not secrets_win.set_password(f, pw):
            set_status("Zapisano config, ale hasła nie udało się zapisać.", error=True)
            return
        if bool(autostart_v.get()) != autostart_win.enabled():
            autostart_win.set_autostart(bool(autostart_v.get()))
        on_saved(new_cfg)
        win.destroy()

    def do_clear():
        for v in (host_v, user_v, remote_v, base_v, pw_v):
            v.set("")
        port_v.set("21")
        passive_v.set(True)
        tls_v.set(False)
        set_status("Wyczyszczono pola (nie zapisano).")

    def do_test():
        f, port = collect_ftp(with_pw_from_field=True)
        if not f.get("host") or not f.get("user"):
            set_status("Uzupełnij Host i User przed testem.", error=True)
            return
        if port is None:
            set_status("Port musi być liczbą.", error=True)
            return
        pw = f.pop("password", None) if not f.get("use_keychain", True) else None
        if pw is None:
            pw = secrets_win.get_password(f)
        tmp = {"ftp": dict(f, use_keychain=True), "public_base_url": ""}
        set_status("Testowanie połączenia…")
        test_btn.config(state="disabled")

        def work():
            try:
                conn = core.ftp_connect(tmp, _NullLog(), timeout=10, password=pw)
                try:
                    conn.quit()
                except Exception:
                    pass
                msg, err = "✓ Połączenie OK.", False
            except Exception as e:  # noqa
                msg, err = f"✗ Błąd: {e}", True
            try:
                win.after(0, lambda: (set_status(msg, err),
                                      test_btn.config(state="normal")))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=3, sticky="we", pady=(12, 0))
    test_btn = ttk.Button(btns, text="Testuj ustawienia", command=do_test)
    test_btn.pack(side="left")
    ttk.Button(btns, text="Wyczyść", command=do_clear).pack(side="left", padx=6)
    ttk.Button(btns, text="Zapisz", command=do_save).pack(side="right")

    if first_run:
        set_status("Uzupełnij dane serwera FTP i publiczny adres URL.")

    win.update_idletasks()
    win.lift()
    win.attributes("-topmost", True)
    win.after(200, lambda: win.attributes("-topmost", False))
    return win
