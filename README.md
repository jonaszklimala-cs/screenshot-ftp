# screenshot-ftp

Obserwuje folder (domyślnie `~/Desktop`). Gdy pojawi się nowy zrzut ekranu zrobiony
**dowolnym programem**, plik jest wysyłany na serwer **FTP**, publiczny URL trafia do
**schowka** i (opcjonalnie) otwiera się w **przeglądarce**.

Sposoby użycia:

- **Aplikacja `.app`** (zalecane) — natywna aplikacja macOS w pasku menu, uruchamiana
  dwuklikiem, bez terminala. Patrz [sekcja 0](#0-aplikacja-app-zalecane).
- **Menu bar ze skryptu** ([menubar.py](menubar.py)) — to samo, ale odpalane z terminala.
- **CLI / headless** ([watcher.py](watcher.py)) — jedyna zależność to `PyYAML`
  (konfiguracja w YAML); poza tym biblioteka standardowa Pythona 3.

> **Ważne:** uruchamiaj tylko JEDEN tryb naraz. Dwa procesy obserwujące ten sam folder
> wyślą każdy zrzut dwa razy.

## 0. Aplikacja `.app` (zalecane)

Domyślnie budowana jako **universal2** — działa natywnie na **Intelu i Apple Silicon**.

### Budowanie

Potrzebny jest **universal2** Python (niesie kod obu architektur). Na macOS jest nim
systemowy `/usr/bin/python3` (Command Line Tools). Z niego tworzymy venv:

```bash
cd /Users/jonaszklimala/dev/screenshot-ftp
/usr/bin/python3 -m venv .venv-u2
.venv-u2/bin/pip install rumps py2app pyyaml
./build_app.sh
```

`build_app.sh` buduje pakiet, usuwa rozszerzenie C PyYAML (`_yaml`, instalowane
per-architektura — dzięki temu YAML działa spójnie na obu) i **podpisuje ad-hoc** (Apple
Silicon nie uruchomi niepodpisanej binarki). Wynik:

- `dist/Screenshot FTP.app` — aplikacja universal2 (~24 MB),
- `dist/Screenshot-FTP-universal2.zip` — spakowana do wysyłki (`ditto`).

Chcesz mniejszy pakiet tylko pod Apple Silicon? `APP_ARCH=arm64 ./build_app.sh`
(≈16 MB; ścienia wszystko do arm64).

Instalacja lokalna:

```bash
cp -R "dist/Screenshot FTP.app" /Applications/
```

### Wysyłka innej osobie — obejście „nieznanego źródła"

Aplikacja jest podpisana tylko **ad-hoc** (nie ma płatnego Apple Developer ID), więc
Gatekeeper na obcym Macu nadal pokaże „z nieznanego źródła". Wyślij `Screenshot-FTP-universal2.zip`
i przekaż odbiorcy jeden z kroków — po rozpakowaniu i przeniesieniu aplikacji:

- **Terminal (najpewniej):**
  ```bash
  xattr -dr com.apple.quarantine "/Applications/Screenshot FTP.app"
  ```
  Usuwa flagę kwarantanny nadaną plikom z internetu — potem otwiera się dwuklikiem.
- **Bez terminala:** dwuklik → blokada → **System Settings → Privacy & Security** → na dole
  **„Open Anyway"** → potwierdź.

Żeby aplikacja otwierała się **u każdego bez żadnych sztuczek**, trzeba ją podpisać
**Developer ID + notaryzować** — wymaga konta Apple Developer (99 USD/rok). Powiedz, jeśli
chcesz — dopiszę do builda kroki `codesign`/`notarytool`/`stapler`.

### Pierwsze uruchomienie

W pasku menu pojawi się ikona `SS→FTP`. Przy pierwszym starcie aplikacja utworzy plik
konfiguracji i **sama otworzy okno Ustawienia** — uzupełnij dane FTP i publiczny URL,
kliknij **Zapisz**, a następnie podaj hasło FTP. Gotowe.

- Konfiguracja aplikacji: `~/Library/Application Support/screenshot-ftp/config.yaml`
  (edytuj przez menu **Ustawienia…**, nie trzeba ruszać terminala).
- macOS może poprosić o dostęp do folderu Pulpit — zezwól.

### Autostart po zalogowaniu

System Settings → **General → Login Items** → **+** → wskaż `Screenshot FTP.app`.
(Nie używaj do tego plików launchd z sekcji 3 — to alternatywa dla wersji skryptowej.)

## Bezpieczeństwo hasła

Hasło FTP **nie jest** trzymane w `config.yaml`. Domyślnie (`ftp.use_keychain: true`) leży
w **Keychain** macOS — zaszyfrowane, powiązane z Twoim kontem, dostępne dopiero po
zalogowaniu. W pliku zostają tylko host, użytkownik i ścieżki.

Jak ustawić / zmienić hasło:

- **Aplikacja / menu bar:** menu **Ustaw hasło FTP…** (bezpieczne pole, hasło idzie prosto
  do Keychain). Przy pierwszej konfiguracji aplikacja poprosi o nie automatycznie.
- **Tryb CLI:**
  ```bash
  .venv/bin/python watcher.py set-password        # zapyta o hasło bez echa
  ```

Hasło można podejrzeć/usunąć też ręcznie w aplikacji **Pęk kluczy (Keychain Access)** —
szukaj pozycji `screenshot-ftp`.

> **Uwaga o transmisji:** Keychain chroni hasło *na dysku*. Zwykły FTP i tak przesyła je
> **jawnie przez sieć**. Dla realnego bezpieczeństwa włącz `ftp.use_tls: true` (FTPS) lub
> przejdź na serwer z SFTP.
>
> **Uwaga przy przekazywaniu aplikacji:** hasło jest w Keychain *Twojego* Maca — nie
> „jedzie" razem z `.app`. Każdy użytkownik ustawia własne hasło u siebie (menu **Ustaw
> hasło FTP…**).

## 1. Konfiguracja

```bash
cd /Users/jonaszklimala/dev/screenshot-ftp
cp config.example.yaml config.yaml
```

Uzupełnij `config.yaml`:

| Pole | Znaczenie |
|------|-----------|
| `watch_dir` | Folder do obserwacji. macOS domyślnie zapisuje zrzuty na Pulpit (`~/Desktop`). |
| `extensions` | Rozszerzenia traktowane jako zrzut. |
| `filename_prefixes` | Opcjonalny filtr nazw (np. `["Screenshot", "Zrzut ekranu"]`). Puste = każdy obraz. |
| `ftp.host/port/user` | Dane logowania FTP. |
| `ftp.use_keychain` | `true` = hasło pobierane z Keychain (zalecane, brak hasła w pliku). Ustaw hasło przez menu **Ustaw hasło FTP…** lub `watcher.py set-password`. |
| `ftp.password` | (opcjonalne, odradzane) hasło w pliku — używane tylko gdy `use_keychain` jest `false`. |
| `ftp.remote_dir` | Katalog docelowy na serwerze (tworzony jeśli nie istnieje). |
| `ftp.passive` | Tryb pasywny (zwykle `true`). |
| `ftp.use_tls` | `true` = FTPS (FTP over TLS). Dla zwykłego FTP zostaw `false`. |
| `public_base_url` | Publiczny URL odpowiadający `remote_dir` (bez końcowego `/`). |
| `copy_url_to_clipboard` | Czy kopiować URL do schowka po wysłaniu (`pbcopy`). |
| `open_in_browser` | Czy otwierać URL w przeglądarce po wysłaniu. |
| `rename_pattern` | Nazwa pliku na serwerze. Zmienne: `{timestamp}`, `{ext}`, `{name}`, `{original}`. |
| `delete_local_after_upload` | Czy kasować lokalny plik po wysłaniu. |

> **Uwaga o nazwie i URL:** jeśli `remote_dir` = `/public_html/screens`, a strona serwuje
> `public_html` jako root domeny, to `public_base_url` = `https://twojadomena/screens`.

## 2a. Tryb menu bar (zalecany do codziennego użytku)

Zależność `rumps` jest już zainstalowana w `.venv`. Uruchomienie:

```bash
/Users/jonaszklimala/dev/screenshot-ftp/.venv/bin/python \
  /Users/jonaszklimala/dev/screenshot-ftp/menubar.py \
  /Users/jonaszklimala/dev/screenshot-ftp/config.yaml
```

W pasku menu pojawi się `SS→FTP`. Menu zawiera:

- status (`● Nasłuchiwanie…` / `✓ Wysłano: …` / `⏸ Wstrzymano`),
- **Ostatnie zrzuty** — klik w pozycję ponownie kopiuje jej URL do schowka,
- przełączniki **Kopiuj URL do schowka** i **Otwieraj w przeglądarce** (na żywo),
- **Ustawienia FTP…** — formularz z osobnymi polami (patrz niżej),
- **Ustawienia zaawansowane (YAML)…** — edytor całego `config.yaml`,
- **Wstrzymaj/Wznów**, **Otwórz folder**, **Otwórz log**, **Zakończ**.

### Okno „Ustawienia FTP…" (formularz)

Natywne okno (AppKit) z polami: **Host, Port, User, Password, Folder** (`remote_dir`),
**Base URL** (`public_base_url`) oraz przełącznikami **Passive mode** i **TLS (FTPS)**.

- **Test settings** — próbuje się połączyć i zalogować na podane dane (z hasłem z pola albo
  z Keychain), wynik pokazuje pod polami. Nie zapisuje niczego.
- **Clear** — czyści pola.
- **Zapisz** — waliduje (Host/User/Port), zapisuje do `config.yaml`, a **hasło do Keychain**
  (pole puste = bez zmian). Zmiany działają od razu (watcher restartuje się sam).

Pola spoza FTP (`watch_dir`, `extensions`, `rename_pattern`, interwały) edytuje się przez
**Ustawienia zaawansowane (YAML)…** — edytor całego pliku. Po **Zapisz** YAML jest walidowany,
zapisywany atomowo (komentarze nie są zachowywane) i stosowany na żywo.

Gdyby `.venv` trzeba było odtworzyć:

```bash
cd /Users/jonaszklimala/dev/screenshot-ftp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## 2b. Test trybu CLI w terminalu

CLI wymaga `PyYAML`, więc użyj Pythona z venv (albo `pip install pyyaml`):

```bash
.venv/bin/python /Users/jonaszklimala/dev/screenshot-ftp/watcher.py /Users/jonaszklimala/dev/screenshot-ftp/config.yaml
```

Zrób zrzut ekranu (`Cmd+Shift+4`). Powinien pojawić się w logu, trafić na FTP i otworzyć
się w przeglądarce. Zatrzymanie: `Ctrl+C`.

## 3. Autostart w tle (launchd)

Wybierz **jeden** plist — dla trybu menu bar albo dla trybu headless (nie oba naraz).

**Tryb menu bar** (ikona w pasku menu, autostart po zalogowaniu):

```bash
cp /Users/jonaszklimala/dev/screenshot-ftp/com.local.screenshot-ftp-menubar.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.local.screenshot-ftp-menubar.plist
```

**Tryb headless** (bez ikony, sam upload w tle):

```bash
cp /Users/jonaszklimala/dev/screenshot-ftp/com.local.screenshot-ftp.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.local.screenshot-ftp.plist
```

Od teraz proces startuje przy logowaniu i restartuje się po awarii.

Zatrzymanie / wyłączenie (użyj tej samej nazwy pliku, którą załadowałeś):

```bash
launchctl unload ~/Library/LaunchAgents/com.local.screenshot-ftp-menubar.plist
```

Po zmianie `config.yaml` przeładuj (unload + load).

## Logi

- Log aplikacji: `~/Library/Logs/screenshot-ftp.log`
- Wyjście launchd: `~/Library/Logs/screenshot-ftp.{out,err}.log`

## Uwagi

- Przy starcie skrypt ignoruje pliki już obecne w folderze — wysyła tylko **nowe**.
- Przed wysyłką czeka, aż rozmiar pliku się ustabilizuje (plik w pełni zapisany).
- Uprawnienia macOS: przy pierwszym uruchomieniu w tle system może poprosić o dostęp do
  folderu Pulpit (System Settings → Privacy & Security → Files and Folders / Full Disk Access).
- Klasyczny FTP przesyła hasło i dane bez szyfrowania. Jeśli serwer wspiera FTPS, ustaw
  `ftp.use_tls: true`.
