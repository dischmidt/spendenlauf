#!/usr/bin/env bash
# Sponsorenlauf-App – Installation und Update auf Ubuntu 24.04 / 26.04 (ohne Docker).
# Mehrfach ausführbar: Ein zweiter Lauf aktualisiert Code und Pakete und lässt .env,
# Daten, htpasswd und die (von certbot ergänzte) nginx-Site unangetastet.
#
#   sudo ./deploy/install.sh --domain spendenlauf.example.org --admin-email admin@example.org --certbot-email admin@example.org
#
# Optionen siehe --help. Das Admin-Passwort wird abgefragt oder per ADMIN_PASSWORD=... übergeben.
set -euo pipefail

NAME="spendenlauf"
DOMAIN="spendenlauf.example.org"
ADMIN_EMAIL=""
CERTBOT_EMAIL=""
PORT="8000"
WITH_NGINX=1
WITH_CERTBOT=1

usage() {
  cat <<EOF
Aufruf: sudo $0 [Optionen]
  --name NAME            Name für Dienst, Systembenutzer, /opt/NAME, /var/lib/NAME, nginx-Site (Standard: $NAME)
  --domain DOMAIN        Domain (Standard: $DOMAIN)
  --admin-email ADRESSE  ADMIN_EMAIL für die .env (Testmails aus dem Admin-Bereich)
  --certbot-email ADR.   E-Mail für Let's Encrypt
  --port PORT            interner Port für gunicorn (Standard: $PORT)
  --no-nginx             nginx nicht einrichten
  --no-certbot           kein Let's-Encrypt-Zertifikat anfordern
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --admin-email) ADMIN_EMAIL="$2"; shift 2 ;;
    --certbot-email) CERTBOT_EMAIL="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --no-nginx) WITH_NGINX=0; WITH_CERTBOT=0; shift ;;
    --no-certbot) WITH_CERTBOT=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; usage; exit 1 ;;
  esac
done

[[ "$NAME" =~ ^[a-z][a-z0-9-]*$ ]] || { echo "--name: nur Kleinbuchstaben, Ziffern und Bindestrich." >&2; exit 1; }
APP_USER="${NAME//-/}"
APP_DIR="/opt/$NAME"
DATA_DIR="/var/lib/$NAME"

step() { printf '\n==> %s\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" || ! "${VERSION_ID:-}" =~ ^(24\.04|26\.04)$ ]]; then
  echo "Hinweis: gedacht für Ubuntu 24.04/26.04, gefunden: ${PRETTY_NAME:-unbekannt}. Fahre trotzdem fort."
fi

step "Pakete"
PKGS=(python3 python3-venv rsync curl)
(( WITH_NGINX )) && PKGS+=(nginx apache2-utils)
(( WITH_CERTBOT )) && PKGS+=(certbot python3-certbot-nginx)
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${PKGS[@]}"
SOFFICE="$(command -v soffice || true)"
if [[ -z "$SOFFICE" ]]; then
  echo "WARNUNG: LibreOffice (soffice) nicht gefunden – die Sponsorenkarte gibt es dann nur als Word-Datei."
  SOFFICE="soffice"
else
  echo "LibreOffice gefunden: $SOFFICE"
fi

step "Systembenutzer und Datenverzeichnis"
id "$APP_USER" &>/dev/null || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$DATA_DIR" "$DATA_DIR/uploads" "$DATA_DIR/backup"

step "Programmdateien nach $APP_DIR"
install -d -m 755 "$APP_DIR"
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  rsync -a --delete \
    --exclude ".env" --exclude ".venv/" --exclude "data/" --exclude "__pycache__/" \
    --exclude ".pytest_cache/" --exclude "*.zip" --exclude ".git/" --exclude ".claude/" \
    "$SRC_DIR/" "$APP_DIR/"
fi
chown -R root:root "$APP_DIR"
chmod +x "$APP_DIR/deploy/install.sh"

step "Python-Umgebung"
[[ -x "$APP_DIR/.venv/bin/python" ]] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q --upgrade -r "$APP_DIR/requirements.txt"
"$APP_DIR/.venv/bin/python" --version

step "Konfiguration (.env)"
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat > "$ENV_FILE" <<EOF
# Geladen per python-dotenv. Mailserver, Vorlagen und alle Angaben zum Lauf stehen im Admin-Bereich.
SECRET_KEY=$SECRET
ADMIN_EMAIL=$ADMIN_EMAIL
BASE_URL=https://$DOMAIN
DATA_DIR=$DATA_DIR
SESSION_COOKIE_SECURE=1
SOFFICE_BIN=$SOFFICE
EOF
  echo "angelegt: $ENV_FILE"
  [[ -n "$ADMIN_EMAIL" ]] || echo "Hinweis: ADMIN_EMAIL ist leer – bitte in $ENV_FILE eintragen."
else
  echo "vorhanden, unverändert: $ENV_FILE"
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

step "systemd-Dienst und Sicherungs-Timer"
render() {
  sed -e "s#@APP_DIR@#$APP_DIR#g" -e "s#@DATA_DIR@#$DATA_DIR#g" \
      -e "s#@APP_USER@#$APP_USER#g" -e "s#@PORT@#$PORT#g" -e "s#@DOMAIN@#$DOMAIN#g" -e "s#@NAME@#$NAME#g" "$1"
}
for suffix in .service -backup.service -backup.timer; do
  render "$APP_DIR/deploy/systemd/app$suffix" > "/etc/systemd/system/$NAME$suffix"
done
systemctl daemon-reload
systemctl enable --quiet "$NAME.service" "$NAME-backup.timer"
systemctl restart "$NAME.service"
systemctl start "$NAME-backup.timer"

printf 'Warte auf die App '
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/robots.txt"; then echo " läuft."; break; fi
  printf '.'; sleep 1
done
curl -fsS -o /dev/null "http://127.0.0.1:$PORT/robots.txt" || {
  echo; echo "Die App antwortet nicht. Log: journalctl -u $NAME -n 50" >&2; exit 1; }

if (( WITH_NGINX )); then
  step "nginx mit Basic Auth für /admin"
  HTPASSWD="/etc/nginx/$NAME.htpasswd"
  if [[ ! -f "$HTPASSWD" ]]; then
    if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
      htpasswd -bcB "$HTPASSWD" admin "$ADMIN_PASSWORD"
    else
      echo "Neues Passwort für den Admin-Bereich (Benutzer: admin):"
      htpasswd -cB "$HTPASSWD" admin
    fi
  else
    echo "vorhanden, unverändert: $HTPASSWD (ändern: sudo htpasswd -B $HTPASSWD admin)"
  fi
  chown root:www-data "$HTPASSWD"
  chmod 640 "$HTPASSWD"

  SITE="/etc/nginx/sites-available/$NAME"
  if [[ ! -f "$SITE" ]]; then
    render "$APP_DIR/deploy/nginx/site.conf" > "$SITE"
    echo "angelegt: $SITE"
  else
    echo "vorhanden, unverändert: $SITE"
  fi
  ln -sf "$SITE" "/etc/nginx/sites-enabled/$NAME"
  nginx -t
  systemctl reload nginx

  if (( WITH_CERTBOT )); then
    step "Let's-Encrypt-Zertifikat"
    MAIL_ARGS=(--register-unsafely-without-email)
    [[ -n "$CERTBOT_EMAIL" ]] && MAIL_ARGS=(-m "$CERTBOT_EMAIL")
    if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --keep-until-expiring --redirect "${MAIL_ARGS[@]}"; then
      echo "HTTPS eingerichtet."
    else
      echo "WARNUNG: certbot fehlgeschlagen. Zeigt der DNS-Eintrag für $DOMAIN auf diesen Server und ist Port 80 offen?"
      echo "Später erneut: sudo certbot --nginx -d $DOMAIN --redirect"
    fi
  fi
fi

step "Fertig"
cat <<EOF
Website:      https://$DOMAIN/
Admin:        https://$DOMAIN/admin   (Benutzer: admin)
Konfiguration $ENV_FILE
Daten:        $DATA_DIR   (Sicherungen täglich 02:30 nach $DATA_DIR/backup)
Logs:         journalctl -u $NAME -f
Update:       neue Version entpacken, dann erneut  sudo ./deploy/install.sh
Nächster Schritt: im Admin-Bereich SMTP-Passwort eintragen und „Verbindung testen“.
EOF
