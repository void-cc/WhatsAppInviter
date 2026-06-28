# WhatsApp Inviter — Go-versie

Native desktop app gebouwd met **Wails v2**, **whatsmeow**, en **excelize**.

## Vereisten

- [Go 1.22+](https://go.dev/dl/)
- [Wails v2](https://wails.io/docs/gettingstarted/installation) (`go install github.com/wailsapp/wails/v2/cmd/wails@latest`)
- Node.js 18+ (voor frontend dev/build)
- Windows 10/11 of macOS

## Ontwikkeling

```bash
cd apps/go
go mod tidy
wails dev
```

## Productie-build

```bash
cd apps/go
build.bat          # Windows
./build_mac.sh     # macOS
```

Output: `build/bin/WhatsAppInviter.exe` of `WhatsAppInviter.app`

## WhatsApp koppelen

1. Start de app → tab **Versturen**
2. Klik **QR-code tonen**
3. Scan met WhatsApp (Instellingen → Gekoppelde apparaten)
4. Sessie wordt opgeslagen in `%APPDATA%\WhatsAppInviter\whatsapp_session.db`

## Architectuur

```
apps/go/
  main.go, app.go           # Wails entry + bindings
  internal/
    phone/                  # Nummernormalisatie
    message/                # {voornaam}/{naam} placeholders
    excel/                  # excelize loader + write-back
    report/                 # CSV export
    settings/               # JSON prefs (gedeeld pad met Python)
    wa/                     # whatsmeow client (QR + send)
  frontend/                 # HTML/CSS/JS wizard UI
```

## Verschil met Python-versie

| | Python | Go |
|---|--------|-----|
| WhatsApp | Browser (pywhatkit) | Direct protocol (whatsmeow) |
| Binary | PyInstaller ~40–80 MB | Native ~15–25 MB |
| Browser nodig | Ja | Nee |
