"""Sciezki i domyslna konfiguracja dla wersji Windows."""

from __future__ import annotations

import os
import sys
import copy
from pathlib import Path

# import watcher.py z katalogu nadrzednego (wspoldzielona logika)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import watcher as core  # noqa: E402

APP_NAME = "screenshot-ftp"


def _appdata() -> str:
    return os.environ.get("APPDATA") or os.path.expanduser("~")


def _localappdata() -> str:
    return os.environ.get("LOCALAPPDATA") or _appdata()


def user_config_path() -> str:
    return os.path.join(_appdata(), APP_NAME, "config.yaml")


def default_log_path() -> str:
    return os.path.join(_localappdata(), APP_NAME, "log.txt")


def default_config() -> dict:
    c = copy.deepcopy(core.DEFAULT_CONFIG)
    # Windows 11: Win+PrtScn zapisuje do Pictures\Screenshots
    c["watch_dir"] = str(Path.home() / "Pictures" / "Screenshots")
    c["log_file"] = default_log_path()
    return c


def ensure_config(path: str) -> bool:
    """Tworzy config.yaml z domyslnych ustawien, jesli nie istnieje. True = utworzono."""
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    core.save_config(path, default_config())
    return True
