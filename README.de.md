# Spendenlauf

🇬🇧 **[English version → README.md](README.md)**

Eine kleine Website für **einen Läufer oder eine Läuferin** bei einem Sponsorenlauf, typischerweise ein Schulkind beim Spendenlauf der Schule. Familie und Freunde sagen einen Betrag pro Runde zu. Die Seite sammelt die Zusagen, zählt am Lauftag die Runden und teilt jedem Sponsor mit, wie viel er zahlt.

> **Ein Läufer pro Installation.** Die App ist auf genau einen Läufer ausgelegt. Es gibt einen Namen, ein Bild, einen Rundenzähler und ein Ergebnis. Mehrere Läufer, Teams oder eine ganze Klasse kann sie nicht verwalten. Für mehrere Läufer braucht jeder eine eigene Installation, oder es braucht die unten beschriebene [Erweiterung für mehrere Läufer](#weiterentwicklung-mehrere-läufer).

Was die App für den Läufer leistet:

- **Vor dem Lauf:** eine öffentliche Seite mit Läuferbild, Countdown und Sponsorenliste. Sponsoren melden sich mit einem Betrag pro Runde an, optional mit Höchstbetrag und Bild, und bestätigen per Mail.
- **Am Lauftag:** Mails „Auf die Plätze“ und „Start“, eine Laufuhr und optional eine Live-Zählung der Runden, bei der sich die Seite selbst aktualisiert. Nach Ablauf der Uhr geht die Mail mit dem vorläufigen Ergebnis raus.
- **Nach dem Lauf:** das Ergebnis (Runden, Strecke, Summe). Jeder Sponsor bekommt eine Zahlungsmail mit seinem persönlichen Betrag und einem PayPal-Link. Zahlungseingänge lassen sich nachhalten, und die ausgefüllte Sponsorenkarte für die Schule gibt es als Word und PDF.

Python 3.12, Flask, SQLite, python-dotenv. Keine externen Skripte, Schriften oder Tracker. Die öffentliche Seite gibt es auf Deutsch und Englisch, der Admin-Bereich ist deutsch.

## Funktionen

**Öffentlich:** Läuferbild auf einer Laufbahn und eine Sponsorenliste mit Miniaturbild (Foto, Logo, Initialen oder ein neutrales Symbol bei anonymen Sponsoren). Sortierung und Seitengröße sind einstellbar. Sponsoren melden sich mit Name, E-Mail, Betrag pro Runde, optionalem Höchstbetrag, optionalem Bild, Anonym-Option und optionalem Wunsch nach Spendenquittung (mit Anschrift) an. Double-Opt-in: Standardmäßig bestätigt der Klick auf den Mail-Link direkt. Eine zusätzliche Bestätigungsseite mit Knopf lässt sich einschalten. Auf dem Desktop zweispaltig, auf dem Handy einspaltig mit Hamburger-Menü, mit Sprachumschaltung Deutsch/Englisch.

**Phasen:** Sponsorensuche → Ergebnis (Summe, Runden und Strecke groß unter dem Bild, Erlös je Sponsor). Optional gibt es einen Countdown bis zum Start und eine Laufuhr mit Live-Zählung, die sich alle 15 Sekunden aktualisiert. „Abgesagt“ überlagert jede Phase und zeigt eine eigene Nachricht.

**Admin** (`/admin`, geschützt per Basic Auth im nginx):

- Übersicht mit Kennzahlen (Zusagen, Summe, bezahlt, offen) und Warnungen
- Sponsoren: Liste mit Miniaturbild, Filter, Bearbeiten, Bestätigen ohne Link, Link erneut senden, Löschen, „bezahlt“ mit Zahlart (PayPal, bar, Überweisung)
- Sponsor anlegen (auch ohne E-Mail, z. B. für Barzahler), optional mit Willkommensmail
- Lauf und Ergebnis:
  - Rundenzähler (+1/−1 oder direkt eintragen)
  - „Lauf starten“ mit Laufuhr und geplanter Startzeit
  - „Endzeit und vorläufige Rundenzahl speichern“ (verschickt die Mail mit dem vorläufigen Ergebnis sofort)
  - Phase, Live-Zählung, Absage mit Nachricht und ein Protokoll der Rundenzahl
- Rundmail mit Platzhaltern und Vorlagen (Training, Erinnerung am Lauftag, Auf die Plätze, Start, Vorläufiges Ergebnis, Ergebnis und Zahlung), Vorschau je Sponsor, Testmail an `ADMIN_EMAIL`, Versand im Hintergrund mit Protokoll und „erneut senden“
- Karte und Export: ausgefüllte Sponsorenkarte der Schule als Word und PDF, CSV-Export, „Alle Daten löschen“
- Einstellungen: alle Angaben zum Läufer (Name auf der Website und auf der Karte, Klasse, Schule, Datum, Rundenlänge, Bild), Seitentexte auf Deutsch und Englisch, Grenzen pro Runde, PayPal-Empfänger und PayPal.me-Name, Impressum, Datenschutzerklärung
- Mailserver und Vorlagen: SMTP-Server, Port, Verschlüsselung, Zugang, Absender, Antwortadresse und Versandpause sowie alle Mailvorlagen mit Bildern, auf Deutsch und Englisch. Der Verbindungstest probiert 587/STARTTLS und 465/SSL und übernimmt die Variante, die funktioniert.

## Weiterentwicklung: mehrere Läufer

Eine naheliegende Weiterentwicklung wäre, die App mandantenfähig zu machen. Dann könnte eine Seite viele Läufer desselben Sponsorenlaufs abbilden, zum Beispiel eine ganze Klasse oder Schule:

- **Ein Admin** für die ganze Seite: Mailserver, Mailvorlagen, Impressum, Datenschutz und Zahlungseinstellungen werden einmal eingerichtet.
- **Ein eigener Bereich pro Läufer** mit eigener öffentlicher Seite (Bild, Texte, Sponsorenliste, Ergebnis) und eigenen Sponsoren und Zusagen. Dazu gehören jeweils ein eigener Rundenzähler, eine Laufuhr, die Phase, Rundmails und die Sponsorenkarte.
- Eine Übersichtsseite zum Lauf, die alle Läufer verlinkt und die Gesamtsumme zeigt.

Das ist noch nicht umgesetzt. Im heutigen Datenmodell liegen die Einstellungen als Schlüssel-Wert-Paare, und Sponsoren haben keinen Bezug zu einem Läufer. Nötig wären eine Läufer-Tabelle und eine Läufer-ID bei Sponsoren, Rundenprotokoll und Rundmails.

## Lokal starten

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # SECRET_KEY setzen, DATA_DIR=./data, SESSION_COOKIE_SECURE=0, BASE_URL=http://127.0.0.1:8000
python wsgi.py                # http://127.0.0.1:8000  und  http://127.0.0.1:8000/admin
pytest
```

Lokal ist `/admin` ungeschützt. Auf dem Server schützt ihn nginx per Basic Auth.

## Konfiguration

In der `.env` (geladen per python-dotenv) stehen nur die technischen Grundwerte:
- `SECRET_KEY`
- `ADMIN_EMAIL`
- `BASE_URL`
- `DATA_DIR`
- `SESSION_COOKIE_SECURE`
- `SOFFICE_BIN`
- optional `DATABASE_FILE` (Dateiname der Datenbank in `DATA_DIR`, Standard `spendenlauf.db`)

Alles andere, auch Mailserver und SMTP-Passwort, wird im Admin-Bereich gepflegt und in der Datenbank gespeichert. Optionale `SMTP_*`-Werte in der `.env` gelten nur als Startwerte beim allerersten Start.

## Installation auf Ubuntu 24.04 / 26.04 (ohne Docker)

Voraussetzungen:
- LibreOffice ist per apt installiert (für den PDF-Export der Sponsorenkarte).
- Der DNS-Eintrag der Domain zeigt auf den Server.
- Port 80 und 443 sind offen.

```bash
git clone https://github.com/dischmidt/spendenlauf.git && cd spendenlauf
sudo ./deploy/install.sh --name spendenlauf --domain spendenlauf.example.org \
  --admin-email admin@example.org --certbot-email admin@example.org
```

`--name` bestimmt Dienst, Systembenutzer (Name ohne Bindestriche), Verzeichnisse und nginx-Site. In der Tabelle unten steht dafür `<name>`. Das Skript fragt das Passwort für den Admin-Bereich ab (oder nimmt `sudo ADMIN_PASSWORD='…' ./deploy/install.sh …`) und richtet ein:

| Was | Wo |
| --- | --- |
| Programm mit Python-venv | `/opt/<name>` (gehört root) |
| Konfiguration (python-dotenv) | `/opt/<name>/.env`, Rechte 640, beim ersten Lauf mit zufälligem `SECRET_KEY` |
| Datenbank, Bilder, Sicherungen | `/var/lib/<name>` (Systembenutzer = Name ohne Bindestriche) |
| Dienst | `<name>.service`: gunicorn auf 127.0.0.1:8000 (`--port`), 1 Prozess, 8 Threads, gehärtet |
| Sicherung | `<name>-backup.timer`: täglich 02:30 nach `/var/lib/<name>/backup`, 14 Tage |
| Webserver | nginx-Site `<name>`, `client_max_body_size 10m`, Basic Auth für `/admin` (`/etc/nginx/<name>.htpasswd`) |
| HTTPS | certbot mit nginx-Plugin, automatische Verlängerung über den certbot-Timer |

Optionen:
- `--name`, `--domain`
- `--port`, wenn 8000 schon belegt ist
- `--no-certbot`, wenn du ein eigenes Zertifikat nutzt
- `--no-nginx`, um nur den App-Dienst einzurichten

`./deploy/install.sh --help` zeigt alle.

**Update:** neue Version holen und `sudo ./deploy/install.sh` mit denselben Optionen (`--name`, `--domain`, `--port`) erneut ausführen. Code und Python-Pakete werden aktualisiert, und der Dienst wird neu gestartet. `.env`, Daten, htpasswd und die von certbot ergänzte nginx-Site bleiben unverändert.

**Nützliche Befehle:**

```bash
journalctl -u spendenlauf -f                              # Log
sudo systemctl restart spendenlauf                        # Neustart, z. B. nach Änderung der .env
sudo htpasswd -B /etc/nginx/spendenlauf.htpasswd admin    # Admin-Passwort ändern
sudo systemctl start spendenlauf-backup                   # Sicherung sofort
```

Hinweise:

- Es darf nur genau ein gunicorn-Prozess laufen, denn SQLite, Ratenbegrenzung und Rundmail-Versand laufen darin. Bitte `--workers` nicht erhöhen.
- Der Dienst läuft mit `ProtectSystem=strict` und darf nur nach `/var/lib/<name>` schreiben. LibreOffice arbeitet in einem privaten `/tmp`.
- Admin- und SMTP-Passwort sollten verschieden sein.

## Checkliste vor dem Livegang

1. Admin → Mailserver und Vorlagen: SMTP-Passwort eintragen und „Verbindung testen“ (Testmail an `ADMIN_EMAIL`).
2. Admin → Einstellungen:
   - Angaben zu Läufer, Schule und Lauf eintragen
   - Impressum und Datenschutzerklärung vervollständigen (Platzhalter stehen in eckigen Klammern)
   - PayPal-Empfänger und ggf. PayPal.me-Namen eintragen
3. Einmal selbst registrieren, die Mail bestätigen und den Eintrag wieder löschen.
4. Den PayPal-Link aus einer Testmail einmal selbst öffnen. Ohne PayPal.me-Namen ist es ein gewöhnlicher PayPal-Zahlungslink an den eingetragenen Empfänger. Dafür fallen beim Empfänger in der Regel Gebühren an. Die Mustervorlage nennt deshalb zusätzlich „Freunde und Familie“ und Barzahlung.

## Am Lauftag und danach

1. Morgens die Rundmail „Erinnerung am Lauftag“ senden.
2. Beim Start „Lauf starten“ klicken. Das startet die Laufuhr und verschickt die Start-Mail, wenn sie eingeschaltet ist. Optional am Streckenrand live mit +1 zählen.
3. Nach dem Lauf Endzeit und vorläufige Rundenzahl speichern. Ist die Mail „Vorläufiges Ergebnis“ eingeschaltet, geht sie dabei raus.
4. Sobald die Rundenzahl bestätigt ist, die Phase „Ergebnis“ wählen und die Rundmail „Ergebnis und Zahlung“ senden (Vorschau, Testmail, dann an alle).
5. Zahlungseingänge als „bezahlt“ markieren. Mit dem Filter „offen“ nachfassen.
6. Die Sponsorenkarte (Word oder PDF) mit dem Umschlag an die Klassenlehrerin geben.
7. Spätestens drei Monate nach dem Lauf: Karte und Export → „Alle Daten löschen“.

## Struktur

```
app/
  __init__.py     App-Factory, .env laden
  db.py           SQLite-Schema und Verbindung
  settings.py     Einstellungen mit Standardwerten und Mailvorlagen
  logic.py        Phasen, Laufuhr, Erlösberechnung (mit Höchstbetrag), Platzhalter
  i18n.py         deutsche und englische Texte der öffentlichen Seite
  public.py       öffentliche Routen
  admin.py        Admin-Routen
  mailer.py       SMTP, Verbindungstest, Rundmail-Versand
  card.py         Sponsorenkarte aus resources/sponsorenkarte.docx
  templates/      Jinja-Templates (öffentlich und admin/)
  static/         CSS, JS, Schriften (OFL), Standardbild
deploy/install.sh Installation und Update auf Ubuntu
deploy/systemd/   Dienst und Sicherungs-Timer
deploy/nginx/     nginx-Site mit Basic Auth
deploy/backup.py  Sicherung von Datenbank und Bildern
tests/            pytest
```

Lizenz: MIT (siehe `LICENSE`). Schriften: Bricolage Grotesque und Atkinson Hyperlegible, SIL Open Font License (Lizenztexte in `app/static/fonts`).
