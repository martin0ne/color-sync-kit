# color-sync-kit

Dopasowanie kolorów i jasności dwóch (lub więcej) ekranów **bez kalibratora sprzętowego** — telefon jako miernik, AI jako matematyk, skrypt jako systemowy filtr punktu bieli.

Powstało, gdy dwa identyczne monitory Dell U2415 za dokiem Thunderbolt odmawiały współpracy z DDC/CI, a kalibrator kosztował tyle, co pół monitora.

## Co zawiera

| Plik | Do czego |
|---|---|
| `docs/poradnik-color-sync-telefon.pdf` | **Zacznij tutaj.** Poradnik krok po kroku dla nie-programisty: pętla strojenia z AI w telefonie + gotowy prompt do wklejenia |
| `wzorzec-color-sync-1920x1200.png` | Wzorzec testowy: 11 pasów szarości + pola 100/50/25/0% |
| `colorsync.py` | Korekta punktu bieli per ekran przez gamma tables macOS (snapshot / apply / reset / status) |
| `colorsync-reapply.py` | Auto-ponawianie korekty co 5 min (gamma tables kasują się po uśpieniu ekranu) |
| `com.mjoldak.colorsync-reapply.plist` | LaunchAgent dla powyższego |

## Szybki start (bez linii komend)

1. Otwórz `docs/poradnik-color-sync-telefon.pdf`.
2. Przygotuj ekrany wg sekcji 3 (True Tone OFF, Contrast 75, Sharpness 50).
3. Wyświetl wzorzec na obu ekranach, zrób jedno zdjęcie, wklej do AI z promptem z poradnika.
4. Wpisz liczby w menu monitora. 2–3 rundy i gotowe.

## Szybki start (Mac, korekta programowa)

```bash
pip3 install pyobjc-framework-Quartz

python3 colorsync.py list                          # id ekranów
python3 colorsync.py apply 3 --rgb 0.93 0.93 0.91  # mnożniki poda AI z pomiaru
python3 colorsync.py status                        # co jest nałożone
python3 colorsync.py reset all                     # cofnij wszystko
```

Pierwsze `apply` robi automatyczny snapshot oryginalnych tablic — `reset` zawsze wraca do stanu fabrycznego, a powtórne `apply` z tym samym mnożnikiem się nie kumuluje (liczy zawsze ze snapshotu).

Auto-odnawianie po uśpieniu ekranu:

```bash
cp colorsync-reapply.py ~/bin/ 2>/dev/null || true
cp com.mjoldak.colorsync-reapply.plist ~/Library/LaunchAgents/
# podmień TWOJ-USER na swoją nazwę użytkownika (polecenie `whoami` pokaże):
sed -i '' "s/TWOJ-USER/$(whoami)/" ~/Library/LaunchAgents/com.mjoldak.colorsync-reapply.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mjoldak.colorsync-reapply.plist
```

Skrypt czyta aktywne korekty z `~/.config/colorsync/state.json` i przywraca je co 5 minut; log w `~/.config/colorsync/reapply.log`.

## Jak to działa

macOS trzyma dla każdego ekranu tablicę transferową (gamma table) — osobno R, G, B: „piksel X ma świecić na Y". `CGSetDisplayTransferByTable` podmienia tę tablicę na poziomie compositora, więc korekta:

- działa **przez dock**, który blokuje DDC/CI (m1ddc/ddcctl tu nic nie zdziałają),
- obejmuje cały obraz — jak f.lux,
- nie dotyka ustawień monitora (OSD) — jasność podświetlenia wpisujesz ręcznie.

Pomiar: zdjęcie obu ekranów w jednej ekspozycji (telefon prostopadle, AE/AF lock, zero refleksów) → mediana (p50) łatki na każdym ekranie → delta → mnożnik = odwrotność delty, jaśniejszy ekran korygowany w dół.

## Ograniczenia

- To **wyrównanie ekranów między sobą**, nie kalibracja do sRGB/DCI — do profesjonalnej pracy z foto: kalibrator hardware (~400–700 zł) + darmowy DisplayCAL.
- Gamma tables kasują się po uśpieniu/resecie ekranu — stąd re-apply automat.
- Czerń laptopa (OLED/mini-LED) zawsze będzie głębsza niż IPS-monitora — wyrównuj biel i jasność, nie czerń.

## Licencja

MIT — rób co chcesz, bez gwarancji.
