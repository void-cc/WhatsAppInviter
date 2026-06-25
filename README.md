# WhatsApp Inviter

Een gebruiksvriendelijke Windows-app om ingeschreven studenten uit te nodigen via WhatsApp. Ontwikkeld voor Bio-informatica en Biomedical Research aan de Hogeschool Leiden.

## Voor eindgebruikers (BM-studenten / medewerkers)

### Wat je nodig hebt

- Windows 10 of 11
- Google Chrome of Microsoft Edge (voor WhatsApp Web)
- Een WhatsApp-account op je telefoon
- Een Excel-bestand (`.xlsx`) met telefoonnummers

### Installatie

**Geen installatie nodig.** Je ontvangt één bestand:

```
WhatsAppInviter.exe
```

Dubbelklik om te starten.

> **Windows SmartScreen-waarschuwing:** Omdat het programma niet digitaal ondertekend is, kan Windows vragen "Windows heeft je pc beschermd". Klik op **Meer info** → **Toch uitvoeren**. Dit is normaal voor interne tools.

### Eenmalig: WhatsApp Web inloggen

1. Open Chrome of Edge
2. Ga naar [web.whatsapp.com](https://web.whatsapp.com)
3. Scan de QR-code met je telefoon
4. Laat de browser open (of zorg dat je de volgende keer weer ingelogd bent)

### Gebruik

1. **Start** `WhatsAppInviter.exe`
2. **Kies Excel-bestand** – selecteer je `.xlsx` export (bijv. uit SANAAM)
3. **Kies werkblad** – als het bestand meerdere tabbladen heeft
4. **Controleer kolommen** – de telefoonkolom wordt automatisch herkend; pas aan indien nodig
5. **Pas het bericht aan** – bewerk de uitnodigingstekst naar wens
6. Klik **Opslaan als standaard** om je bericht en instellingen te bewaren voor volgende keren
7. Klik **Start versturen**
8. De app opent WhatsApp Web per student en verstuurt het bericht
9. Met **Bevestig na elk bericht** aan: klik **Volgende** om door te gaan, of **Stop** om te stoppen

### Excel-formaat

- Bestandstype: `.xlsx` (Excel)
- De app zoekt automatisch de tabelkop (hoef niet in cel A1 te staan)
- Kolom met telefoonnummers wordt herkend op namen zoals: *Mobiel telefoonnummer*, *telefoon*, *gsm*, *phone*
- Nederlandse nummers (`06-...` of `0612345678`) worden automatisch omgezet naar `+31...`

### Instellingen opslaan

Je bericht, landcode en kolomkeuzes worden opgeslagen in:

```
%APPDATA%\WhatsAppInviter\settings.json
```

---

## Voor ontwikkelaars / onderhoud

### Lokaal draaien (zonder exe)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Exe bouwen

Dubbelklik op `build.bat` of voer uit in de projectmap:

```bash
build.bat
```

Output: `dist\WhatsAppInviter.exe`

De build-script:
1. Maakt een virtual environment aan
2. Installeert alle dependencies
3. Bouwt één standalone `.exe` met PyInstaller

### Projectstructuur

```
app.py                  # GUI (customtkinter)
core/
  excel_loader.py       # Excel inlezen, kolommen detecteren
  phone.py              # Telefoonnummer normalisatie
  sender.py             # WhatsApp versturen via pywhatkit
  settings.py           # Instellingen opslaan in AppData
assets/
  default_message.txt   # Standaard uitnodigingstekst
main.py                 # Oud console-script (legacy)
build.bat               # Eén-klik build
app.spec                # PyInstaller configuratie
requirements.txt
```

### Bekende beperkingen

- Berichten worden verstuurd via **WhatsApp Web automatisering** (zelfde methode als het oude script). Dit vereist een ingelogde browsersessie en kan af en toe traag of gevoelig zijn voor browser-updates.
- WhatsApp kan bulk-berichten beperken; gebruik **Bevestig na elk bericht** voor controle.
- Alleen `.xlsx` wordt ondersteund (geen `.csv` in de GUI; het oude `main.py` ondersteunt nog wel CSV).

### Oude script

Het originele console-script staat nog in `main.py` voor referentie. Gebruik `app.py` / `WhatsAppInviter.exe` voor dagelijks gebruik.
