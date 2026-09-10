"""Autostart przy logowaniu (Windows) — klucz rejestru HKCU ...\\Run."""

from __future__ import annotations

import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "screenshot-ftp"


def _launch_command() -> str:
    """Komenda uruchamiajaca aplikacje przy logowaniu."""
    if getattr(sys, "frozen", False):
        # spakowany .exe (PyInstaller)
        return f'"{sys.executable}"'
    # tryb skryptowy: python app_win.py
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_win.py")
    return f'"{sys.executable}" "{script}"'


def enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_autostart(on: bool) -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ,
                                  _launch_command())
            else:
                try:
                    winreg.DeleteValue(k, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
