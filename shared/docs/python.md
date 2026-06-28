# WhatsApp Inviter — Python-versie

Zie ook het [hoofd-README](../../README.md) voor het monorepo-overzicht.

## Voor eindgebruikers

### Wat je nodig hebt

- Windows 10 of 11 (of macOS voor de `.app`-build)
- Google Chrome of Microsoft Edge (voor WhatsApp Web)
- Een WhatsApp-account op je telefoon
- Een Excel-bestand (`.xlsx`) met telefoonnummers

### Installatie

Download vanuit [Latest release](https://github.com/void-cc/WhatsAppInviter/releases/latest) `WhatsAppInviter-windows.exe` of `WhatsAppInviter-macOS.zip`.

### Eenmalig: WhatsApp Web inloggen

1. Open Chrome of Edge
2. Ga naar [web.whatsapp.com](https://web.whatsapp.com)
3. Scan de QR-code met je telefoon

### Gebruik

1. Start `WhatsAppInviter.exe`
2. Kies Excel-bestand → werkblad → kolommen
3. Pas bericht aan (`{voornaam}` / `{naam}`)
4. Start versturen

Zie de volledige handleiding in de eerdere README-secties (checkbox-kolom, bereik, rapport export).

---

## Voor ontwikkelaars

### Lokaal draaien

```bash
cd apps/python
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Windows exe bouwen

```bash
cd apps/python
build.bat
```

Output: `apps/python/dist/WhatsAppInviter.exe`

### macOS app bouwen

```bash
cd apps/python
chmod +x build_mac.sh
./build_mac.sh
```

Output: `apps/python/dist/WhatsAppInviter.app`

### Projectstructuur (python)

```
apps/python/
  app.py              # GUI (customtkinter)
  core/               # excel, phone, message, sender, settings, report
  requirements.txt
  app.spec            # PyInstaller
  build.bat / build_mac.sh
shared/assets/        # default_message.txt (gedeeld met Go-app)
```
