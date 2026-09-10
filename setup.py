"""
Buduje natywna aplikacje macOS (.app) z menubar.py przy uzyciu py2app.

Uzycie:
    .venv/bin/python setup.py py2app        # pelny build -> dist/Screenshot FTP.app
    .venv/bin/python setup.py py2app -A     # tryb "alias" (szybki, do testow lokalnych)

Wynik: dist/Screenshot FTP.app
"""

import os

from setuptools import setup

# Docelowa architektura. Domyslnie universal2 (dziala na Intelu i Apple Silicon).
# Mozna zawezic:  APP_ARCH=arm64 .venv/bin/python setup.py py2app
APP_ARCH = os.environ.get("APP_ARCH", "universal2")

APP = ["menubar.py"]

# Bundlujemy tez modul logiki i szablon konfiguracji.
DATA_FILES = ["config.example.yaml"]

OPTIONS = {
    "argv_emulation": False,        # WAZNE: True potrafi zawieszac aplikacje menu bar
    "arch": APP_ARCH,               # arm64 = natywnie na Apple Silicon
    "packages": ["rumps", "yaml"],
    "includes": ["watcher", "settings_window"],  # lokalne moduly
    "optimize": 2,                  # bytecode -OO (usuwa docstringi/asserty)
    # Odchudzenie pakietu: wyklucz nieuzywane, ciezkie moduly (mniejszy bundle,
    # mniej ladowania przy starcie). Nic z tego nie jest importowane przez aplikacje.
    "excludes": [
        "tkinter", "Tkinter", "turtle", "turtledemo",
        "test", "unittest", "doctest",
        "lib2to3", "pydoc", "pydoc_data", "idlelib",
        "ensurepip", "pip", "setuptools", "wheel", "pkg_resources",
        "distutils", "venv",
        "sqlite3", "xmlrpc", "pdb", "curses",
    ],
    "plist": {
        "CFBundleName": "Screenshot FTP",
        "CFBundleDisplayName": "Screenshot FTP",
        "CFBundleIdentifier": "com.local.screenshot-ftp",
        "CFBundleVersion": "1.0.1",
        "CFBundleShortVersionString": "1.0.1",
        # Aplikacja tylko w pasku menu - bez ikony w Docku i bez okna glownego.
        "LSUIElement": True,
        "NSHumanReadableCopyright": "",
    },
}

setup(
    name="Screenshot FTP",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
