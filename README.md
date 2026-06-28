# WhatsApp Inviter

Een gebruiksvriendelijke app om ingeschreven studenten uit te nodigen via WhatsApp. Ontwikkeld voor Bio-informatica en Biomedis aan de Hogeschool Leiden.

Dit is een **monorepo** met twee implementaties:

| App | Pad | Stack | Status |
|-----|-----|-------|--------|
| **Python (legacy)** | [`apps/python/`](apps/python/) | customtkinter + pywhatkit | Stabiel, PyInstaller `.exe` |
| **Go (nieuw)** | [`apps/go/`](apps/go/) | Wails + whatsmeow + excelize | Native binary, geen browser |

Gedeelde assets staan in [`shared/assets/`](shared/assets/).

---

## Snel starten

### Python-versie (bestaand)

```bash
cd apps/python
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python app.py
```

Build: `build.bat` (Windows) of `build_mac.sh` (macOS) vanuit `apps/python/`.

### Go-versie (nieuw)

Vereist [Go 1.22+](https://go.dev/dl/) en [Wails v2](https://wails.io/docs/gettingstarted/installation).

```bash
cd apps/go
go mod tidy
wails dev          # ontwikkeling
wails build        # productie-binary
```

Build-scripts: `build.bat` / `build_mac.sh` vanuit `apps/go/`.

Output: `apps/go/build/bin/WhatsAppInviter.exe` (Windows) of `.app` (macOS).

---

## Verschil tussen de twee apps

| | Python | Go |
|---|--------|-----|
| **WhatsApp** | Browser-automatisering (WhatsApp Web + Chrome) | Direct via WhatsApp multi-device protocol (QR-koppeling) |
| **Binary-grootte** | ~40–80 MB (PyInstaller) | ~15–25 MB (native) |
| **Browser nodig** | Ja | Nee |
| **Excel** | openpyxl | excelize |
| **Instellingen** | `%APPDATA%\WhatsAppInviter\settings.json` | Zelfde pad (gedeeld) |

---

## Gebruikersdocumentatie

Zie [`shared/docs/python.md`](shared/docs/python.md) voor de volledige handleiding (Excel-formaat, placeholders, checkbox-kolom, etc.). De Go-app volgt dezelfde workflow (3 stappen: Importeren → Bericht → Versturen).

### Go-versie: WhatsApp koppelen

1. Start de app
2. Ga naar **Versturen**
3. Klik **QR-code tonen**
4. Scan met WhatsApp op je telefoon (Instellingen → Gekoppelde apparaten)
5. Sessie blijft bewaard; volgende keer hoef je niet opnieuw te scannen

---

## Projectstructuur

```
apps/
  python/          # customtkinter GUI + pywhatkit sender
  go/              # Wails GUI + whatsmeow sender
shared/
  assets/          # default_message.txt
  docs/            # gebruikers- en ontwikkelaarsdocs
.github/workflows/ # CI builds voor beide apps
```

---

## CI / Releases

GitHub Actions bouwt bij push naar `master`/`main` en op tags (`v*`) **beide** apps voor Windows en macOS. Artifacts staan onder Actions; releases bevatten alle vier binaries.

---

## Bekende beperkingen

- **whatsmeow** is een unofficial WhatsApp client library (zelfde grijze zone als pywhatkit, maar betrouwbaarder dan browser-automatisering).
- WhatsApp kan bulk-berichten beperken; gebruik **Bevestig na elk bericht** voor controle.
- Alleen `.xlsx` wordt ondersteund.
