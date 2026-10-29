# screenshot-ftp

Aplikacja macOS w pasku menu. Obserwuje folder (domyślnie `~/Desktop`); gdy pojawi się
nowy zrzut ekranu zrobiony **dowolnym programem**, wysyła go na **FTP**, kopiuje publiczny
**URL do schowka** i (opcjonalnie) otwiera w przeglądarce.
Dymyslenie wspierane rozszerzenia plików:
- dla obrazów - ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".bmp"
- dla wideo - ".mp4", ".mov", ".webm"

## Instalacja i pierwsze uruchomienie

1. Pobierz `Screenshot-FTP-universal2.zip` z **[najnowszego wydania](../../releases/latest)**
   (uniwersalny — Intel i Apple Silicon).
2. Rozpakuj i przenieś **`Screenshot FTP.app`** do `/Applications`.
3. Uruchom — w pasku menu pojawi się ikona `SS→FTP`. Przy pierwszym starcie aplikacja
   sama otworzy okno **Ustawienia FTP** (patrz niżej).


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

Gdy aplikacja jest uruchomiona, znajdziesz ją na pasku menu. Kliknij w **ikonkę*** → **Ustawienia FTP…**, otwiera to okno z konfiguracją.
Dane do pól oznaczonych &ast; znajdziesz w **Bitwarden**, w notatce **„Monosnap - configuration"**.


| Pole | Znaczenie |
|------|-----------|
| **Host / Port / User / Password** &ast; | Dane logowania FTP (hasło jest zapisywane w macOSowym Keychain). |
| **Zdalny folder** &ast; | Katalog docelowy na serwerze Creativecast, do którego zostanie przesłany plik (jeśli katalog nie istnieje, zostanie utworzony). |
| **Base URL** &ast; | Publiczny adres odpowiadający zdalnemu folderowi (bez końcowego `/`). |
| **Obserwuj** | Lista folderów śledzonych pod zrzuty (jeden na linię; **Dodaj folder…** pozwala wskazać wiele naraz). |
| **Przeszukuj podfoldery** | Gdy zaznaczone — śledzi też wszystkie podfoldery wskazanych folderów. |
| **Passive mode / TLS (FTPS)** | Tryb pasywny i szyfrowanie połączenia. |
| **Uruchamiaj przy logowaniu** | Autostart aplikacji (LaunchAgent). |


Przyciski: **Testuj ustawienia** (próba połączenia, wynik pod przyciskami; nic nie
zapisuje), **Wyczyść**, **Zapisz** (zapis + hasło do Keychain, zmiany działają od razu).


**WAŻNE** Jeśli używasz monosnapa, pamiętaj, by screeny i filmiki zapisywać we wskazanych w konfiguratorze folderach, a nie klikać "upload."

## Konfiguracja zaawansowana (YAML) - opcjonalne, jak chcesz pogrzebać

Menu → **Ustawienia zaawansowane (YAML)…** to edytor całego pliku `config.yaml` — dla pól,
których nie ma w formularzu:

| Pole | Znaczenie |
|------|-----------|
| `extensions` | Tu można dodać rozszerzenia plików, które chcielibyśmy wrzucać na serwer (np. `[".png", ".jpg"]`). |
| `filename_prefixes` | Opcjonalna reguła, poszukuje tylko plików z konkretnymi wyrazami w nazwie, np. `["Screenshot", "Zrzut ekranu"]`); puste = każdy obraz. |
| `poll_interval_seconds` | Odstęp trybu zapasowego. Normalnie folder jest śledzony zdarzeniowo (kqueue, bez odpytywania); ta wartość działa tylko w fallbacku i jako odstęp sprawdzania stabilności pliku. |
| `stable_checks` | Ile odczytów stałego rozmiaru, zanim plik zostanie wysłany. |
| `rename_pattern` | Nazwa pliku na serwerze. Zmienne: `{timestamp}`, `{ext}`, `{name}`, `{original}`. |
| `copy_url_to_clipboard` / `open_in_browser` | Co zrobić po wysłaniu. |
| `delete_local_after_upload` | Czy kasować lokalny plik po wysłaniu. |
| `log_file` | Ścieżka logu. |


## Historia wersji

### v1.1.0
- **Wiele obserwowanych folderów** oraz opcja **„Przeszukuj podfoldery"**
  (rekurencyjnie) — w formularzu i w configu (`watch_dirs`, `watch_recursive`).
- Dotyczy macOS i Windows. Stary `watch_dir` nadal działa (zgodność wsteczna).
- Domyślnie wysyłane są też pliki **wideo**: `.mp4`, `.mov`, `.webm`.

### v1.0.1
- Śledzenie folderu **zdarzeniowe** (kqueue) zamiast odpytywania — zero wybudzeń
  w bezczynności, oszczędza baterię. Polling pozostaje jako tryb zapasowy.
- Lżejszy pakiet (mniej modułów, `optimize=2`): ~22 MB, nieco mniej RAM.

### v1.0.0
- Obserwacja folderu i automatyczna wysyłka zrzutów na FTP.
- Kopiowanie publicznego URL do schowka + otwieranie w przeglądarce.
- Aplikacja w pasku menu (universal2: Intel + Apple Silicon).
- Formularz **Ustawienia FTP** z testem połączenia, wyborem folderu i autostartem.
- Edytor zaawansowany **config.yaml**.
- Hasło FTP przechowywane w **Keychain**.

---

<sub>Budowanie ze źródeł: `./build_app.sh` (wymaga venv z universal2 Pythona — `/usr/bin/python3` — z `rumps`, `py2app`, `pyyaml`).</sub>
