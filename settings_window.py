#!/usr/bin/env python3
"""
Natywne okno ustawien FTP (AppKit / PyObjC) — prawdziwy formularz z polami:
Host, Port, User, Password, Folder (remote_dir), Base URL, Passive mode, TLS,
oraz przyciski Test settings / Clear / Zapisz.

Haslo trafia do Keychain (nie do pliku), spojnie z reszta aplikacji.
Uzywane przez menubar.py (pozycja "Ustawienia FTP…").
"""

from __future__ import annotations

import threading

import os
import sys

from Foundation import NSObject, NSMakeRect, NSBundle
from AppKit import (
    NSWindow, NSView, NSTextField, NSSecureTextField, NSButton, NSApp,
    NSOpenPanel, NSModalResponseOK,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSBackingStoreBuffered, NSSwitchButton, NSBezelStyleRounded,
    NSTextAlignmentRight, NSFont, NSColor,
)
from PyObjCTools import AppHelper
import objc

import watcher as core


# --- geometria ---
W = 500             # szerokosc okna
LABEL_X = 16
LABEL_W = 108
FIELD_X = 132
FIELD_W = 336
ROW_H = 24
ROW_STEP = 34
PAD = 18


class _FlippedView(NSView):
    """Widok z ukladem wspolrzednych od gory (y rosnie w dol) — latwiej ukladac wiersze."""
    def isFlipped(self):
        return True


class SettingsController(NSObject):
    """Kontroler okna ustawien. Tworzony przez open_settings_form()."""

    # obiekty i dane przypisujemy po alloc().init() (PyObjC pozwala na atrybuty pythonowe)

    @objc.python_method
    def _label(self, container, y, text):
        lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(LABEL_X, y + 2, LABEL_W, ROW_H))
        lbl.setStringValue_(text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setAlignment_(NSTextAlignmentRight)
        lbl.setFont_(NSFont.systemFontOfSize_(13))
        container.addSubview_(lbl)

    @objc.python_method
    def _field(self, container, y, width, secure=False):
        cls = NSSecureTextField if secure else NSTextField
        f = cls.alloc().initWithFrame_(NSMakeRect(FIELD_X, y, width, ROW_H))
        f.setFont_(NSFont.systemFontOfSize_(13))
        container.addSubview_(f)
        return f

    @objc.python_method
    def _checkbox(self, container, x, y, title, width=150):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, ROW_H))
        b.setButtonType_(NSSwitchButton)
        b.setTitle_(title)
        container.addSubview_(b)
        return b

    @objc.python_method
    def _button(self, container, x, y, w, title, action, default=False):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 30))
        b.setBezelStyle_(NSBezelStyleRounded)
        b.setTitle_(title)
        b.setTarget_(self)
        b.setAction_(action)
        if default:
            b.setKeyEquivalent_("\r")
        container.addSubview_(b)
        return b

    @objc.python_method
    def buildWindow(self):
        ftp = self.cfg.get("ftp", {}) or {}

        # wiersze: host, port(+checkboxy), user, pass, zdalny, baseurl, obserwuj,
        # autostart = 8
        rows = 8
        # + wiersz przyciskow (2+30) + odstep (8) + status (ROW_H) + dolny margines
        content_h = PAD + rows * ROW_STEP + (2 + 30 + 8 + ROW_H) + PAD
        rect = NSMakeRect(0, 0, W, content_h)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        win.setTitle_("Ustawienia FTP")
        win.setReleasedWhenClosed_(False)

        container = _FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, W, content_h))
        win.setContentView_(container)

        y = PAD
        # Host
        self._label(container, y, "Host:")
        self.host = self._field(container, y, FIELD_W)
        self.host.setStringValue_(str(ftp.get("host", "")))
        y += ROW_STEP
        # Port + Passive + TLS
        self._label(container, y, "Port:")
        self.port = self._field(container, y, 70)
        self.port.setStringValue_(str(ftp.get("port", 21)))
        self.passive = self._checkbox(container, FIELD_X + 84, y, "Passive mode")
        self.passive.setState_(1 if ftp.get("passive", True) else 0)
        self.tls = self._checkbox(container, FIELD_X + 220, y, "TLS (FTPS)")
        self.tls.setState_(1 if ftp.get("use_tls", False) else 0)
        y += ROW_STEP
        # User
        self._label(container, y, "User:")
        self.user = self._field(container, y, FIELD_W)
        self.user.setStringValue_(str(ftp.get("user", "")))
        y += ROW_STEP
        # Password (secure) — z Keychain; puste = bez zmian
        self._label(container, y, "Password:")
        self.password = self._field(container, y, FIELD_W, secure=True)
        has_pw = core.keychain_get_password(ftp) is not None
        # NSSecureTextField: placeholder informuje o stanie
        try:
            self.password.setPlaceholderString_(
                "(zapisane — puste = bez zmian)" if has_pw else "(wpisz hasło)")
        except Exception:
            pass
        y += ROW_STEP
        # Zdalny folder (remote_dir)
        self._label(container, y, "Zdalny folder:")
        self.remote_dir = self._field(container, y, FIELD_W)
        self.remote_dir.setStringValue_(str(ftp.get("remote_dir", "")))
        y += ROW_STEP
        # Base URL
        self._label(container, y, "Base URL:")
        self.base_url = self._field(container, y, FIELD_W)
        self.base_url.setStringValue_(str(self.cfg.get("public_base_url", "")))
        y += ROW_STEP
        # Obserwowany folder (watch_dir) + przycisk wyboru
        self._label(container, y, "Obserwuj:")
        self.watch_dir = self._field(container, y, FIELD_W - 92)
        self.watch_dir.setStringValue_(str(self.cfg.get("watch_dir", "")))
        self._button(container, FIELD_X + FIELD_W - 84, y - 3, 84,
                     "Wybierz…", "chooseFolder:")
        y += ROW_STEP
        # Autostart przy logowaniu
        self.autostart = self._checkbox(container, FIELD_X, y,
                                        "Uruchamiaj przy logowaniu", width=260)
        self.autostart.setState_(1 if core.autostart_enabled() else 0)
        y += ROW_STEP

        # wiersz przyciskow
        by = y + 2
        self._button(container, LABEL_X, by, 140, "Testuj ustawienia",
                     "testSettings:")
        self._button(container, LABEL_X + 148, by, 80, "Wyczyść", "clearFields:")
        self._button(container, W - 96 - PAD, by, 96, "Zapisz", "save:", default=True)

        # status (komunikat testu) — POD przyciskami
        sy = by + 30 + 8
        self.status = NSTextField.alloc().initWithFrame_(
            NSMakeRect(LABEL_X, sy, W - 2 * LABEL_X, ROW_H))
        self.status.setBezeled_(False)
        self.status.setDrawsBackground_(False)
        self.status.setEditable_(False)
        self.status.setSelectable_(False)
        self.status.setFont_(NSFont.systemFontOfSize_(11))
        self.status.setTextColor_(NSColor.secondaryLabelColor())
        self.status.setStringValue_("")
        container.addSubview_(self.status)

        self.window = win
        win.center()
        NSApp().activateIgnoringOtherApps_(True)
        win.makeKeyAndOrderFront_(None)

    # --- pomocnicze ---
    @objc.python_method
    def _collect_ftp(self, with_password_from_field=False):
        """Buduje slownik ftp z pol formularza."""
        try:
            port = int(str(self.port.stringValue()).strip() or "21")
        except ValueError:
            port = None
        ftp = dict(self.cfg.get("ftp", {}) or {})
        ftp["host"] = str(self.host.stringValue()).strip()
        if port is not None:
            ftp["port"] = port
        ftp["user"] = str(self.user.stringValue()).strip()
        ftp["remote_dir"] = str(self.remote_dir.stringValue()).strip()
        ftp["passive"] = bool(self.passive.state())
        ftp["use_tls"] = bool(self.tls.state())
        ftp["use_keychain"] = True
        ftp.pop("password", None)
        if with_password_from_field:
            pw = str(self.password.stringValue())
            if pw:
                # tryb testu: nie ruszamy Keychain, podajemy haslo wprost
                ftp = dict(ftp, use_keychain=False, password=pw)
        return ftp, port

    @objc.python_method
    def _set_status(self, text, error=False):
        self.status.setStringValue_(text)
        self.status.setTextColor_(
            NSColor.systemRedColor() if error else NSColor.secondaryLabelColor())

    @objc.python_method
    def _launch_args(self):
        """Komenda, ktora LaunchAgent ma uruchamiac przy logowaniu.

        W wersji .app -> `open <bundle>`; w trybie skryptu -> python menubar.py cfg.
        Rozroznienie po sys.frozen, ktore py2app ustawia tylko w spakowanej aplikacji
        (unikamy falszywego wykrycia Python.app systemowego interpretera).
        """
        if getattr(sys, "frozen", None):
            bpath = NSBundle.mainBundle().bundlePath() or ""
            if bpath.endswith(".app"):
                return ["/usr/bin/open", bpath]
        menubar_py = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "menubar.py")
        return [sys.executable, menubar_py, self.cfg_path]

    # --- akcje (selektory ObjC) ---
    def save_(self, sender):
        ftp, port = self._collect_ftp()
        if not ftp["host"] or not ftp["user"]:
            self._set_status("Host i User są wymagane.", error=True)
            return
        if port is None:
            self._set_status("Port musi być liczbą.", error=True)
            return

        new_cfg = dict(self.cfg)
        new_cfg["ftp"] = ftp
        new_cfg["public_base_url"] = str(self.base_url.stringValue()).strip()
        watch = str(self.watch_dir.stringValue()).strip()
        if watch:
            new_cfg["watch_dir"] = watch

        try:
            core.save_config(self.cfg_path, new_cfg)
        except OSError as e:
            self._set_status(f"Błąd zapisu: {e}", error=True)
            return

        # haslo -> Keychain (tylko gdy pole niepuste)
        pw = str(self.password.stringValue())
        if pw:
            if not core.keychain_set_password(ftp, pw):
                self._set_status("Zapisano config, ale hasła nie udało się "
                                 "zapisać w Keychain.", error=True)
                return

        # autostart — zsynchronizuj z checkboxem (tylko gdy stan sie zmienil)
        want_autostart = bool(self.autostart.state())
        if want_autostart != core.autostart_enabled():
            core.set_autostart(want_autostart, self._launch_args())

        self.cfg = new_cfg
        self.app.apply_new_config(new_cfg)
        self.window.close()

    def chooseFolder_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(True)
        panel.setCanChooseFiles_(False)
        panel.setAllowsMultipleSelection_(False)
        panel.setPrompt_("Wybierz")
        if panel.runModal() == NSModalResponseOK:
            urls = panel.URLs()
            if urls and len(urls):
                self.watch_dir.setStringValue_(urls[0].path())

    def clearFields_(self, sender):
        for f in (self.host, self.user, self.remote_dir, self.base_url,
                  self.password):
            f.setStringValue_("")
        self.port.setStringValue_("21")
        self.passive.setState_(1)
        self.tls.setState_(0)
        self._set_status("Wyczyszczono pola (nie zapisano).")

    def testSettings_(self, sender):
        ftp, port = self._collect_ftp(with_password_from_field=True)
        if not ftp.get("host") or not ftp.get("user"):
            self._set_status("Uzupełnij Host i User przed testem.", error=True)
            return
        if port is None:
            self._set_status("Port musi być liczbą.", error=True)
            return
        # jesli pole hasla puste, sprobujemy Keychain (use_keychain zostaje True)
        tmp = {"ftp": ftp, "public_base_url": ""}
        self._set_status("Testowanie połączenia…")
        sender.setEnabled_(False)

        def work():
            try:
                conn = core.ftp_connect(tmp, self.app.log, timeout=10)
                try:
                    conn.quit()
                except Exception:
                    pass
                msg, err = "✓ Połączenie OK (zalogowano, folder dostępny).", False
            except Exception as e:  # noqa
                msg, err = f"✗ Błąd: {e}", True
            AppHelper.callAfter(self._test_done, sender, msg, err)

        threading.Thread(target=work, daemon=True).start()

    @objc.python_method
    def _test_done(self, sender, msg, err):
        sender.setEnabled_(True)
        self._set_status(msg, error=err)


def open_settings_form(app, cfg: dict, cfg_path: str) -> "SettingsController":
    """Tworzy i pokazuje okno ustawien. Zwraca kontroler (trzymaj referencje!)."""
    ctrl = SettingsController.alloc().init()
    ctrl.app = app
    ctrl.cfg = cfg
    ctrl.cfg_path = cfg_path
    ctrl.buildWindow()
    return ctrl
