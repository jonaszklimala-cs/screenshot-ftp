"""Haslo FTP w Windows Credential Manager (przez bibliotekę keyring).

Odpowiednik macOS Keychain — hasło zaszyfrowane, powiązane z kontem użytkownika.
"""

from __future__ import annotations

import keyring

SERVICE = "screenshot-ftp"


def account(ftp: dict) -> str:
    return f"{ftp.get('user', '')}@{ftp.get('host', '')}:{ftp.get('port', 21)}"


def get_password(ftp: dict) -> str | None:
    try:
        return keyring.get_password(SERVICE, account(ftp)) or None
    except Exception:
        return None


def set_password(ftp: dict, password: str) -> bool:
    try:
        keyring.set_password(SERVICE, account(ftp), password)
        return True
    except Exception:
        return False


def delete_password(ftp: dict) -> bool:
    try:
        keyring.delete_password(SERVICE, account(ftp))
        return True
    except Exception:
        return False
