# Spendenlauf

Website für den Sponsorenlauf eines Schulkinds. Sponsoren sagen einen Betrag pro Runde zu, bestätigen per E-Mail-Link und erscheinen danach in der Liste. Nach dem Lauf trägt der Admin die Runden ein, die Seite zeigt Ergebnis und Erlöse, und eine Rundmail schickt jedem Sponsor seinen Betrag mit PayPal-Link.

Python 3.12, Flask, SQLite, python-dotenv. Keine externen Skripte, Schriften oder Tracker.

## Funktionen

Öffentlich: Läuferbild auf einer Laufbahn, Sponsorenliste mit Miniaturbild (Foto, Logo, Initialen oder neutrales Symbol bei anonymen Sponsoren), sortiert nach Betrag pro Runde. Registrierung mit Name, E-Mail, Betrag pro Runde, optionalem Höchstbetrag, optionalem Bild, Anonym-Option und optionalem Wunsch nach Spendenquittung (mit Anschrift). Double-Opt-in: Der Link öffnet eine Seite mit Bestätigungsknopf, damit Link-Scanner von Mailprogrammen nichts auslösen. Desktop-Layout zweispaltig, auf dem Handy einspaltig mit Hamburger-Menü.

Phasen: Sponsorensuche → Ergebnis (Summe, Runden und Strecke groß unter dem Bild, Erlös je Sponsor). Optional Live-Zählung mit automatischer Aktualisierung alle 15 Sekunden. „Abgesagt“ überlagert jede Phase und zeigt eine eigene Nachricht.

Admin (`/admin`, Basic Auth im nginx):

- Übersicht mit Kennzahlen (Zusagen, Summe, bezahlt, offen) und Warnungen
- Sponsoren: Liste mit Miniaturbild, Filter, Bearbeiten, Bestätigen ohne Link, Link erneut senden, Löschen, „bezahlt“ mit Zahlart (PayPal, bar, Überweisung)
- Sponsor anlegen (auch ohne E-Mail, z. B. für Barzahler), optional mit Willkommensmail
- Lauf und Ergebnis: Rundenzähler (+1/−1 oder direkt), Phase, optionale Live-Zählung, Absage mit Nachricht, Protokoll
- Rundmail mit Platzhaltern, zwei Mustervorlagen (Erinnerung am Lauftag, Ergebnis und Zahlung), Vorschau je Sponsor, Testmail an `ADMIN_EMAIL`, Versand im Hintergrund mit Protokoll und „erneut senden“
- Karte und Export: ausgefüllte Sponsorenkarte der Schule als Word und PDF („Opt-In per Email-Bestätigung“ in der Unterschrift-Spalte bei Link-Bestätigung), CSV-Export, „Alle Daten löschen“
- Einstellungen: alle Angaben zum Läufer bzw. zur Läuferin (Name auf der Website und auf der Karte, Klasse, Schule, Datum, Rundenlänge, Bild), Seitentexte, Obergrenze pro Runde, PayPal-Empfänger und PayPal.me-Name, Impressum, Datenschutzerklärung
- Mailserver und Vorlagen: SMTP-Server, Port, Verschlüsselung, Zugang, Absender, Antwortadresse, Versandpause, alle Mailvorlagen; Verbindungstest probiert 587/STARTTLS und 465/SSL und übernimmt die funktionierende Variante

## Lokal starten

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # SECRET_KEY setzen, DATA_DIR=./data, SESSION_COOKIE_SECURE=0, BASE_URL=http://127.0.0.1:8000
python wsgi.py                # http://127.0.0.1:8000  und  http://127.0.0.1:8000/admin
pytest
```

Lokal ist `/admin` ungeschützt – auf dem Server schützt ihn nginx per Basic Auth.

## Konfiguration

In der `.env` (geladen per python-dotenv) stehen nur die technischen Grundwerte: `SECRET_KEY`, `ADMIN_EMAIL`, `BASE_URL`, `DATA_DIR`, `SESSION_COOKIE_SECURE`, `SOFFICE_BIN` und optional `DATABASE_FILE` (Dateiname der Datenbank in `DATA_DIR`, Standard `spendenlauf.db`). Alles andere – inklusive Mailserver und SMTP-Passwort – wird im Admin-Bereich gepflegt und in der Datenbank gespeichert. Optionale `SMTP_*`-Werte in der `.env` gelten nur als Startwerte beim allerersten Start.

## Installation auf Ubuntu 24.04 / 26.04 (ohne Docker)

Voraussetzungen: LibreOffice ist per apt installiert (für den PDF-Export der Sponsorenkarte), der DNS-Eintrag der Domain zeigt auf den Server, Port 80 und 443 sind offen.

```bash
git clone <repo-url> spendenlauf && cd spendenlauf
sudo ./deploy/install.sh --name spendenlauf --domain spendenlauf.example.org \
  --admin-email admin@example.org --certbot-email admin@example.org
```

`--name` bestimmt Dienst, Systembenutzer (Name ohne Bindestriche), Verzeichnisse und nginx-Site; in der Tabelle steht `<name>`.

Das Skript fragt das Passwort für den Admin-Bereich ab (oder `sudo ADMIN_PASSWORD='…' ./deploy/install.sh …`) und richtet ein:

| Was | Wo |
| --- | --- |
| Programm mit Python-venv | `/opt/<name>` (gehört root) |
| Konfiguration (python-dotenv) | `/opt/<name>/.env`, Rechte 640, beim ersten Lauf mit zufälligem `SECRET_KEY` |
| Datenbank, Bilder, Sicherungen | `/var/lib/<name>` (Systembenutzer = Name ohne Bindestriche) |
| Dienst | `<name>.service`: gunicorn auf 127.0.0.1:8000 (`--port`), 1 Prozess, 8 Threads, gehärtet |
| Sicherung | `<name>-backup.timer`: täglich 02:30 nach `/var/lib/<name>/backup`, 14 Tage |
| Webserver | nginx-Site `<name>`, `client_max_body_size 10m`, Basic Auth für `/admin` (`/etc/nginx/<name>.htpasswd`) |
| HTTPS | certbot mit nginx-Plugin, automatische Verlängerung über den certbot-Timer |

Optionen: `--name`, `--domain`, `--port` (wenn 8000 schon belegt ist), `--no-certbot` (eigenes Zertifikat), `--no-nginx` (nur App-Dienst). `./deploy/install.sh --help` zeigt alle.

**Update:** neue Version holen und `sudo ./deploy/install.sh` mit denselben Optionen (`--name`, `--domain`, `--port`) erneut ausführen. Code und Python-Pakete werden aktualisiert und der Dienst neu gestartet; `.env`, Daten, htpasswd und die von certbot ergänzte nginx-Site bleiben unverändert.

**Nützliche Befehle:**

```bash
journalctl -u spendenlauf -f                       # Log
sudo systemctl restart spendenlauf                 # Neustart, z. B. nach Änderung der .env
sudo htpasswd -B /etc/nginx/spendenlauf.htpasswd admin   # Admin-Passwort ändern
sudo systemctl start spendenlauf-backup            # Sicherung sofort
```

Hinweise:

- Genau ein gunicorn-Prozess: SQLite, Ratenbegrenzung und Rundmail-Versand laufen darin. Bitte `--workers` nicht erhöhen.
- Der Dienst läuft mit `ProtectSystem=strict` und darf nur nach `/var/lib/<name>` schreiben; LibreOffice arbeitet in einem privaten `/tmp`.
- Das Admin- und das SMTP-Passwort sollten verschieden sein.

## Checkliste vor dem Livegang

1. Admin → Mailserver und Vorlagen: SMTP-Passwort eintragen, „Verbindung testen“ (Testmail an `ADMIN_EMAIL`).
2. Admin → Einstellungen: Angaben zu Läufer, Schule und Lauf eintragen, Impressum und Datenschutzerklärung vervollständigen (Platzhalter in eckigen Klammern), PayPal-Empfänger und ggf. PayPal.me-Namen eintragen.
3. Einmal selbst registrieren, Mail bestätigen, Eintrag wieder löschen.
4. Den PayPal-Link aus einer Testmail einmal selbst öffnen. Ohne PayPal.me-Namen ist es ein gewöhnlicher PayPal-Zahlungslink an den eingetragenen PayPal-Empfänger; dafür fallen in der Regel Gebühren beim Empfänger an. Die Mustervorlage nennt deshalb zusätzlich „Freunde und Familie“ und Barzahlung.

## Am Lauftag und danach

1. Morgens Rundmail „Erinnerung am Lauftag“.
2. Optional: Live-Zählung einschalten und am Streckenrand mit +1 zählen.
3. Nach dem Lauf Runden eintragen, Phase „Ergebnis“ wählen.
4. Rundmail „Ergebnis und Zahlung“ (Vorschau, Testmail, dann an alle).
5. Zahlungseingänge als „bezahlt“ markieren; Filter „offen“ zum Nachfassen.
6. Sponsorenkarte (Word oder PDF) mit dem Umschlag an die Klassenlehrerin.
7. Spätestens drei Monate nach dem Lauf: Karte und Export → „Alle Daten löschen“.

## Struktur

```
app/
  __init__.py     App-Factory, .env laden
  db.py           SQLite-Schema und Verbindung
  settings.py     Einstellungen mit Standardwerten und Mailvorlagen
  logic.py        Phasen, Erlösberechnung (mit Höchstbetrag), Platzhalter
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
