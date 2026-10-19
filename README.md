# Spendenlauf

🇩🇪 **[Deutsche Version → README.de.md](README.de.md)**

A small website for **one runner** in a sponsored run, typically a school child in a school fundraising run. Family and friends pledge an amount per lap. The site collects the pledges, counts the laps on race day, and tells every sponsor what they owe.

> **One runner per installation.** The app is built around exactly one runner. It has one name, one photo, one lap counter and one result. It cannot manage several runners, teams or a whole class. For several runners you would need a separate installation for each, or the [multi-runner extension](#roadmap-several-runners) described below.

What it does for the runner:

- **Before the run:** a public page with the runner's photo, a countdown and the sponsor list. Sponsors sign up with a per-lap amount, an optional cap and an optional picture, and confirm by email.
- **On race day:** "on your marks" and start emails, a race clock, and optional live lap counting with an auto-refreshing page. After the clock runs out, a provisional result email goes out.
- **After the run:** the result (laps, distance, total). Each sponsor gets a payment email with their personal amount and a PayPal link. Payments can be tracked, and a filled-in sponsor card for the school can be exported as Word or PDF.

Python 3.12, Flask, SQLite, python-dotenv. No external scripts, fonts or trackers. The public site is available in German and English. The admin area is in German.

## Features

**Public site:** runner photo on a running track, and a sponsor list with thumbnails (photo, logo, initials, or a neutral symbol for anonymous sponsors). Sort order and page size are configurable. Sponsors sign up with name, email, amount per lap, an optional maximum, an optional picture, an "anonymous" option and an optional donation receipt request (with address). Double opt-in: by default the email link confirms directly, and an extra confirmation page with a button can be switched on. Two-column layout on desktop, single column with a hamburger menu on phones, language switch German/English.

**Phases:** sponsor collection → result (total, laps and distance shown large under the photo, amount per sponsor). There is an optional countdown to the start and a race clock with live counting (refreshes every 15 seconds). "Cancelled" overrides every phase and shows its own message.

**Admin** (`/admin`, protected by nginx basic auth):

- Dashboard with key figures (pledges, total, paid, open) and warnings
- Sponsors: list with thumbnails, filters, editing, confirming without the link, resending the link, deleting, and marking as paid with payment method (PayPal, cash, bank transfer)
- Adding sponsors manually (also without email, e.g. for cash payers), optionally with a welcome email
- Run and result:
  - lap counter (+1/−1 or direct entry)
  - start button with race clock and planned start time
  - "save end time and provisional lap count" (sends the provisional result email right away)
  - phase, live counting, cancellation with a message, and a log of lap count changes
- Group email with placeholders and templates (training, race day reminder, on your marks, start, provisional result, result and payment), preview per sponsor, test email to `ADMIN_EMAIL`, and background sending with a log and "send again"
- Sponsor card and export: the school's sponsor card, filled in, as Word and PDF; CSV export; "delete all data"
- Settings: everything about the runner (name on the website and on the card, class, school, date, lap length, photo), page texts in German and English, limits per lap, PayPal recipient and PayPal.me name, imprint, privacy policy
- Mail server and templates: SMTP server, port, encryption, login, sender, reply-to and sending delay, plus all mail templates with images, in German and English. The connection test tries 587/STARTTLS and 465/SSL and keeps the one that works.

## Roadmap: several runners

A natural next step is to make the app multi-tenant, so that one site serves many runners in the same sponsored run (for example a whole class or school):

- **One admin** for the whole site: mail server, mail templates, imprint, privacy policy and payment settings are set up once.
- **One area per runner** with its own public page (photo, texts, sponsor list, result), its own sponsors and pledges, lap counter, race clock, phase, group emails and sponsor card.
- An overview page for the run that links to all runners and shows the combined total.

This is not implemented yet. Today's data model (settings as key/value pairs, sponsors without a runner reference) would need a runner table and a runner ID on sponsors, lap logs and group emails.

## Run locally

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # set SECRET_KEY, DATA_DIR=./data, SESSION_COOKIE_SECURE=0, BASE_URL=http://127.0.0.1:8000
python wsgi.py                # http://127.0.0.1:8000  and  http://127.0.0.1:8000/admin
pytest
```

Locally, `/admin` is not protected. On the server, nginx protects it with basic auth.

## Configuration

The `.env` file (loaded by python-dotenv) only holds the technical basics:
- `SECRET_KEY`
- `ADMIN_EMAIL`
- `BASE_URL`
- `DATA_DIR`
- `SESSION_COOKIE_SECURE`
- `SOFFICE_BIN`
- optionally `DATABASE_FILE` (database file name in `DATA_DIR`, default `spendenlauf.db`)

Everything else, including the mail server and the SMTP password, is managed in the admin area and stored in the database. Optional `SMTP_*` values in `.env` are only used as initial values on the very first start.

## Installation on Ubuntu 24.04 / 26.04 (without Docker)

Prerequisites:
- LibreOffice is installed via apt (for the PDF export of the sponsor card).
- The domain's DNS record points to the server.
- Ports 80 and 443 are open.

```bash
git clone https://github.com/dischmidt/spendenlauf.git && cd spendenlauf
sudo ./deploy/install.sh --name spendenlauf --domain spendenlauf.example.org \
  --admin-email admin@example.org --certbot-email admin@example.org
```

`--name` sets the service, the system user (the name without hyphens), the directories and the nginx site. The table below writes it as `<name>`. The script asks for the admin password (or takes `sudo ADMIN_PASSWORD='…' ./deploy/install.sh …`) and sets up:

| What | Where |
| --- | --- |
| Program with Python venv | `/opt/<name>` (owned by root) |
| Configuration (python-dotenv) | `/opt/<name>/.env`, mode 640, created on the first run with a random `SECRET_KEY` |
| Database, images, backups | `/var/lib/<name>` (system user = name without hyphens) |
| Service | `<name>.service`: gunicorn on 127.0.0.1:8000 (`--port`), 1 process, 8 threads, hardened |
| Backup | `<name>-backup.timer`: daily at 02:30 into `/var/lib/<name>/backup`, keeps 14 days |
| Web server | nginx site `<name>`, `client_max_body_size 10m`, basic auth for `/admin` (`/etc/nginx/<name>.htpasswd`) |
| HTTPS | certbot with the nginx plugin, automatic renewal via the certbot timer |

Options:
- `--name`, `--domain`
- `--port`, if 8000 is already taken
- `--no-certbot`, if you use your own certificate
- `--no-nginx`, to install only the app service

`./deploy/install.sh --help` lists them all.

**Update:** pull the new version and run `sudo ./deploy/install.sh` again with the same options (`--name`, `--domain`, `--port`). Code and Python packages are updated and the service is restarted. `.env`, data, htpasswd and the nginx site (as extended by certbot) stay untouched.

**Useful commands:**

```bash
journalctl -u spendenlauf -f                              # log
sudo systemctl restart spendenlauf                        # restart, e.g. after changing .env
sudo htpasswd -B /etc/nginx/spendenlauf.htpasswd admin    # change the admin password
sudo systemctl start spendenlauf-backup                   # back up now
```

Notes:

- Run exactly one gunicorn process. SQLite, rate limiting and group email sending all run inside it, so please don't increase `--workers`.
- The service runs with `ProtectSystem=strict` and may only write to `/var/lib/<name>`. LibreOffice works in a private `/tmp`.
- Use different passwords for the admin area and for SMTP.

## Checklist before going live

1. Admin → Mailserver und Vorlagen: enter the SMTP password and click "Verbindung testen" (sends a test email to `ADMIN_EMAIL`).
2. Admin → Einstellungen:
   - enter the runner, school and run details
   - complete the imprint and privacy policy (placeholders are in square brackets)
   - enter the PayPal recipient and, optionally, a PayPal.me name
3. Sign up once yourself, confirm the email, then delete the entry.
4. Open the PayPal link from a test email once. Without a PayPal.me name it is a regular PayPal payment link to the configured recipient, which usually costs the recipient fees. The template therefore also mentions "Friends and Family" and cash.

## On race day and afterwards

1. In the morning, send the group email "race day reminder".
2. At the start, click "Lauf starten" (starts the race clock and sends the start email if it is enabled). Optionally count laps live with +1 at the track.
3. After the run, enter the end time and the provisional lap count. The provisional result email goes out if it is enabled.
4. Once the lap count is confirmed, choose the phase "Ergebnis" and send the group email "result and payment" (preview, test email, then to everyone).
5. Mark incoming payments as paid. Use the "open" filter to follow up.
6. Hand the sponsor card (Word or PDF) to the class teacher together with the envelope.
7. No later than three months after the run: Karte und Export → "Alle Daten löschen".

## Structure

```
app/
  __init__.py     app factory, loads .env
  db.py           SQLite schema and connection
  settings.py     settings with defaults and mail templates
  logic.py        phases, race clock, amount calculation (with cap), placeholders
  i18n.py         German/English texts for the public site
  public.py       public routes
  admin.py        admin routes
  mailer.py       SMTP, connection test, group email sending
  card.py         sponsor card from resources/sponsorenkarte.docx
  templates/      Jinja templates (public and admin/)
  static/         CSS, JS, fonts (OFL), default image
deploy/install.sh installation and update on Ubuntu
deploy/systemd/   service and backup timer
deploy/nginx/     nginx site with basic auth
deploy/backup.py  backup of database and images
tests/            pytest
```

License: MIT (see `LICENSE`). Fonts: Bricolage Grotesque and Atkinson Hyperlegible, SIL Open Font License (license texts in `app/static/fonts`).
