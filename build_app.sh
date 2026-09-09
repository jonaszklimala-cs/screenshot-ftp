#!/bin/bash
# Buduje natywna aplikacje macOS dla Apple Silicon: dist/Screenshot FTP.app (arm64).
# Wymaga venv opartego na universal2 Pythonie (/usr/bin/python3) z rumps + py2app.
# Zobacz README, sekcja 0.
set -euo pipefail
cd "$(dirname "$0")"

VENV="${VENV:-.venv-u2}"
APP_ARCH="${APP_ARCH:-arm64}"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Brak $VENV. Utworz je z universal2 Pythona:"
  echo "  /usr/bin/python3 -m venv $VENV && $VENV/bin/pip install rumps py2app"
  exit 1
fi

echo "Czyszczenie poprzedniego builda…"
rm -rf build dist

echo "Budowanie aplikacji (arch=$APP_ARCH)…"
APP_ARCH="$APP_ARCH" "$VENV/bin/python" setup.py py2app

APP="dist/Screenshot FTP.app"

# py2app scienia tylko glowny stub; framework Pythona i .so zostaja universal2.
# Jesli budujemy pod jedna architekture, scieniamy caly pakiet (mniejszy, spojny).
if [ "$APP_ARCH" = "arm64" ] || [ "$APP_ARCH" = "x86_64" ]; then
  echo "Scienianie wszystkich binariow Mach-O do: $APP_ARCH…"
  count=0
  while IFS= read -r f; do
    archs=$(lipo -archs "$f" 2>/dev/null) || continue
    case "$archs" in
      *" "*)  # binarka uniwersalna (kilka architektur) -> scien
        if printf '%s\n' "$archs" | grep -qw "$APP_ARCH"; then
          lipo -thin "$APP_ARCH" "$f" -output "$f" 2>/dev/null && count=$((count+1))
        fi
        ;;
    esac
  done < <(find "$APP" -type f \( -perm -u+x -o -name "*.so" -o -name "*.dylib" -o -name "Python" \))
  echo "Scieniono $count plikow."
fi

# Apple Silicon wymaga podpisu (min. ad-hoc), inaczej system nie uruchomi binarki.
# lipo uniewaznil ewentualne podpisy, wiec podpisujemy ad-hoc na koniec.
echo "Podpisywanie ad-hoc…"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "Podpis OK (ad-hoc)."

# Spakuj do .zip zachowujac strukture pakietu (bezpieczna wysylka).
ZIP="dist/Screenshot-FTP-arm64.zip"
ditto -c -k --keepParent "$APP" "$ZIP"

echo
echo "Gotowe:"
echo "  Aplikacja: $APP  ($(lipo -archs "$APP/Contents/MacOS/Screenshot FTP"))"
echo "  Do wysylki: $ZIP"
echo "Zainstaluj lokalnie:  cp -R '$APP' /Applications/"
