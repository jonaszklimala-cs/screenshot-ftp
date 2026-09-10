# screenshot-ftp

Aplikacja macOS w pasku menu. Obserwuje folder (domyślnie `~/Desktop`); gdy pojawi się
nowy zrzut ekranu zrobiony **dowolnym programem**, wysyła go na **FTP**, kopiuje publiczny
**URL do schowka** i (opcjonalnie) otwiera w przeglądarce.

## Instalacja i pierwsze uruchomienie

1. Pobierz `Screenshot-FTP-universal2.zip` z **[najnowszego wydania](../../releases/latest)**
   (uniwersalny — Intel i Apple Silicon).
2. Rozpakuj i przenieś **`Screenshot FTP.app`** do `/Applications`.
3. Uruchom — w pasku menu pojawi się ikona `SS→FTP`. Przy pierwszym starcie aplikacja
   sama otworzy okno **Ustawienia FTP** (patrz niżej).

Konfiguracja trafia do `~/Library/Application Support/screenshot-ftp/config.yaml`,
a hasło FTP do **Keychain** (nie do pliku).

### Obejście „z nieznanego źródła"

Aplikacja jest podpisana tylko ad-hoc (bez płatnego Apple Developer ID), więc przy
pierwszym uruchomieniu Gatekeeper ją zablokuje. Odblokowanie — jedno z:

- **Terminal** (najpewniej), po przeniesieniu do `/Applications`:
  ```bash
  xattr -dr com.apple.quarantine "/Applications/Screenshot FTP.app"
  ```
- **Bez terminala:** dwuklik → komunikat o blokadzie → **System Settings → Privacy &
  Security** → na dole **„Open Anyway"** → potwierdź.

macOS może też poprosić o dostęp do folderu Pulpit — zezwól.

## Konfiguracja — formularz

Menu paska → **Ustawienia FTP…** otwiera okno z polami:

| Pole | Znaczenie |
|------|-----------|
| **Host / Port / User / Password** | Dane logowania FTP (hasło → Keychain; puste = bez zmian). |
| **Zdalny folder** | Katalog docelowy na serwerze (tworzony, jeśli nie istnieje). |
| **Base URL** | Publiczny adres odpowiadający zdalnemu folderowi (bez końcowego `/`). |
| **Obserwuj** | Folder śledzony pod zrzuty (przycisk **Wybierz…** otwiera wybór folderu). |
| **Passive mode / TLS (FTPS)** | Tryb pasywny i szyfrowanie połączenia. |
| **Uruchamiaj przy logowaniu** | Autostart aplikacji (LaunchAgent). |

Przyciski: **Testuj ustawienia** (próba połączenia, wynik pod przyciskami; nic nie
zapisuje), **Wyczyść**, **Zapisz** (zapis + hasło do Keychain, zmiany działają od razu).

## Konfiguracja zaawansowana (YAML)

Menu → **Ustawienia zaawansowane (YAML)…** to edytor całego pliku `config.yaml` — dla pól,
których nie ma w formularzu:

| Pole | Znaczenie |
|------|-----------|
| `extensions` | Rozszerzenia traktowane jako zrzut (np. `[".png", ".jpg"]`). |
| `filename_prefixes` | Filtr nazw (np. `["Screenshot", "Zrzut ekranu"]`); puste = każdy obraz. |
| `poll_interval_seconds` | Jak często sprawdzać folder. |
| `stable_checks` | Ile odczytów stałego rozmiaru, zanim plik zostanie wysłany. |
| `rename_pattern` | Nazwa pliku na serwerze. Zmienne: `{timestamp}`, `{ext}`, `{name}`, `{original}`. |
| `copy_url_to_clipboard` / `open_in_browser` | Co zrobić po wysłaniu. |
| `delete_local_after_upload` | Czy kasować lokalny plik po wysłaniu. |
| `log_file` | Ścieżka logu. |

Po **Zapisz** plik jest walidowany i stosowany od razu (komentarze nie są zachowywane).

## Historia wersji

### v1.0.0
- Obserwacja folderu i automatyczna wysyłka zrzutów na FTP.
- Kopiowanie publicznego URL do schowka + otwieranie w przeglądarce.
- Aplikacja w pasku menu (universal2: Intel + Apple Silicon).
- Formularz **Ustawienia FTP** z testem połączenia, wyborem folderu i autostartem.
- Edytor zaawansowany **config.yaml**.
- Hasło FTP przechowywane w **Keychain**.

---

<sub>Budowanie ze źródeł: `./build_app.sh` (wymaga venv z universal2 Pythona — `/usr/bin/python3` — z `rumps`, `py2app`, `pyyaml`). Wydania powstają automatycznie z tagów `vX.Y.Z` przez GitHub Actions.</sub>
