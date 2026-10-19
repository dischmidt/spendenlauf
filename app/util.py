"""Hilfsfunktionen: Geldbeträge, Bilder, CSRF, Ratenbegrenzung, Platzhalter, Jinja-Filter."""
import hashlib
import hmac
import io
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from flask import abort, current_app, request, session
from markupsafe import Markup, escape
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

BERLIN = ZoneInfo("Europe/Berlin")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- Zeit

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def in_days_iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


def parse_iso(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def fmt_dt(value, with_time=True):
    dt = parse_iso(value) if isinstance(value, str) else value
    if not dt:
        return ""
    dt = dt.astimezone(BERLIN)
    return dt.strftime("%d.%m.%Y %H:%M") if with_time else dt.strftime("%d.%m.%Y")


def fmt_date_de(iso_date):
    """'2026-09-25' -> '25.09.2026'"""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso_date or ""


def fmt_relative(value):
    """'vor wenigen Sekunden' / 'vor X Minuten' / 'vor Y Stunden' / 'vor Z Tagen'."""
    from .i18n import t, tn

    dt = parse_iso(value) if isinstance(value, str) else value
    if not dt:
        return ""
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 60:
        return t("zeit.gerade_eben")
    if seconds < 3600:
        n = int(seconds // 60)
        return t("zeit.vor", n=n, einheit=tn("zeit.minute", n))
    if seconds < 86400:
        n = int(seconds // 3600)
        return t("zeit.vor", n=n, einheit=tn("zeit.stunde", n))
    n = int(seconds // 86400)
    return t("zeit.vor", n=n, einheit=tn("zeit.tag", n))


# ---------------------------------------------------------------- Geld

def parse_euro(raw):
    """'1,50' / '1.50' / '2' / '1,50 €' -> 150 (Cent). ValueError bei ungültiger Eingabe."""
    if raw is None:
        raise ValueError("leer")
    s = str(raw).strip().replace("€", "").replace(" ", "")
    if not s:
        raise ValueError("leer")
    if "," in s and "." in s:          # 1.234,50
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError("keine Zahl") from exc
    if d.as_tuple().exponent < -2:
        raise ValueError("höchstens zwei Nachkommastellen")
    if d < 0:
        raise ValueError("negativ")
    return int((d * 100).to_integral_value())


def fmt_euro(cents, symbol=True):
    if cents is None:
        return ""
    cents = int(cents)
    euros, rest = divmod(abs(cents), 100)
    text = f"{euros:,}".replace(",", ".") + f",{rest:02d}"
    if cents < 0:
        text = "-" + text
    return f"{text} €" if symbol else text


def euro_input(cents):
    """Für Formularfelder: 150 -> '1,50'"""
    return "" if cents in (None, "") else fmt_euro(cents, symbol=False).replace(".", "")


def fmt_km(meters):
    km = Decimal(int(meters)) / Decimal(1000)
    text = f"{km:.2f}".rstrip("0").rstrip(".") if km % 1 else f"{int(km)}"
    return text.replace(".", ",") + " km"


# ---------------------------------------------------------------- Tokens

def new_token():
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- Bilder

class ImageError(ValueError):
    pass


def _open_image(file_storage):
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageError("Das Bild konnte nicht gelesen werden. Bitte JPG, PNG oder WebP verwenden.") from exc
    if img.format not in {"JPEG", "PNG", "WEBP", "GIF", "MPO"}:
        raise ImageError("Bitte ein Bild als JPG, PNG oder WebP hochladen.")
    return ImageOps.exif_transpose(img)


def save_sponsor_image(file_storage, size=400):
    """Quadratisch zuschneiden, Metadaten verwerfen, als JPEG speichern."""
    img = _open_image(file_storage)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img = ImageOps.fit(img, (size, size), Image.LANCZOS, centering=(0.5, 0.4))
    name = f"s-{uuid.uuid4().hex}.jpg"
    img.save(Path(current_app.config["UPLOAD_DIR"]) / name, "JPEG", quality=85, optimize=True)
    return name


def save_runner_image(file_storage, max_side=1000):
    """Läuferbild: Transparenz bleibt erhalten (PNG)."""
    img = _open_image(file_storage)
    img = img.convert("RGBA")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    name = f"l-{uuid.uuid4().hex}.png"
    img.save(Path(current_app.config["UPLOAD_DIR"]) / name, "PNG", optimize=True)
    return name


def save_mail_image(file_storage, max_side=1200):
    """Bild für Mailvorlagen: verkleinern, Metadaten verwerfen, als JPEG speichern."""
    img = _open_image(file_storage)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    name = f"m-{uuid.uuid4().hex}.jpg"
    img.save(Path(current_app.config["UPLOAD_DIR"]) / name, "JPEG", quality=85, optimize=True)
    return name


def bild_namen(value):
    """Gespeicherte Bildliste (ein Dateiname pro Zeile) -> Liste gültiger Namen."""
    return [n for n in (value or "").split() if re.fullmatch(r"m-[0-9a-f]{32}\.jpg", n)]


def bild_urls(value):
    base = current_app.config["BASE_URL"]
    return [f"{base}/bild/{n}" for n in bild_namen(value)]


OG_SIZE = (1200, 630)
OG_TRACK = (31, 95, 168)      # --track
OG_LANE_SEP = (230, 240, 248)  # --ice, entspricht dem weißen Bahnstreifen auf --track
OG_LINE = (244, 196, 48)      # --lane


def render_og_image(runner_path):
    """Läuferbild auf der Bahn-Grafik der Website freistellen, für og:image (Linkvorschau in sozialen Netzwerken)."""
    w, h = OG_SIZE
    canvas = Image.new("RGB", (w, h), OG_TRACK)
    draw = ImageDraw.Draw(canvas)
    for i in (1, 2, 3):
        x = round(w / 4 * i)
        draw.rectangle([x - 2, 0, x + 2, h], fill=OG_LANE_SEP)
    line_bottom = round(h * 0.87) + 6
    draw.rectangle([0, line_bottom - 6, w, line_bottom], fill=OG_LINE)

    runner = Image.open(runner_path).convert("RGBA")
    target_h = round(h * 0.8)
    target_w = max(1, round(runner.width * target_h / runner.height))
    runner = runner.resize((target_w, target_h), Image.LANCZOS)
    canvas.paste(runner, ((w - target_w) // 2, line_bottom - target_h), runner)

    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=85, optimize=True)
    return buf.getvalue()


def delete_upload(name):
    if not name or "/" in name or ".." in name:
        return
    path = Path(current_app.config["UPLOAD_DIR"]) / name
    if path.exists():
        path.unlink()


def initials(name):
    parts = [p for p in re.split(r"[\s\-]+", name or "") if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# ---------------------------------------------------------------- Platzhalter

PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def render_placeholders(text, ctx):
    return PLACEHOLDER_RE.sub(lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx else m.group(0), text or "")


def used_placeholders(text):
    return set(PLACEHOLDER_RE.findall(text or ""))


def text_to_html(text):
    """Klartext -> einfaches HTML mit Absätzen und klickbaren Links."""
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        html = str(escape(block))
        html = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', html)
        out.append("<p>" + html.replace("\n", "<br>") + "</p>")
    return "\n".join(out)


def paypal_link(settings, cents, sponsor_name=""):
    amount = f"{int(cents) / 100:.2f}"
    me = (settings.get("paypal_me") or "").strip().strip("/")
    if me:
        me = me.rsplit("/", 1)[-1]
        return f"https://paypal.me/{quote(me)}/{amount}EUR"
    receiver = (settings.get("paypal_empfaenger") or "").strip()
    if not receiver:
        return ""
    params = {
        "cmd": "_xclick",
        "business": receiver,
        "amount": amount,
        "currency_code": "EUR",
        "item_name": f"Sponsorenlauf {settings.get('laeufer_name', '')} – {sponsor_name}".strip(" –"),
        "no_shipping": "1",
    }
    return "https://www.paypal.com/cgi-bin/webscr?" + urlencode(params)


# ---------------------------------------------------------------- CSRF

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_field():
    return Markup(f'<input type="hidden" name="_csrf" value="{csrf_token()}">')


def check_csrf():
    if request.method != "POST" or current_app.config.get("TESTING_NO_CSRF"):
        return
    sent = request.form.get("_csrf", "")
    if not sent or not hmac.compare_digest(sent, session.get("_csrf", "")):
        abort(400, "Das Formular ist abgelaufen. Bitte lade die Seite neu und versuche es noch einmal.")


# ---------------------------------------------------------------- Ratenbegrenzung

class RateLimiter:
    """Einfacher In-Prozess-Zähler; reicht, weil die App mit genau einem Prozess läuft."""

    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def hit(self, key, limit, window_seconds):
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window_seconds]
            allowed = len(hits) < limit
            if allowed:
                hits.append(now)
            self._hits[key] = hits
            return allowed


limiter = RateLimiter()


def client_ip():
    return request.remote_addr or "unbekannt"


# ---------------------------------------------------------------- Flask-Anbindung

def nl2p(text):
    return Markup(text_to_html(text))


def init_app(app):
    app.before_request(check_csrf)
    app.jinja_env.globals.update(csrf_field=csrf_field, initials=initials, bild_namen=bild_namen)
    app.jinja_env.filters.update(
        euro=fmt_euro, dt=fmt_dt, datum=fmt_date_de, km=fmt_km, nl2p=nl2p, euro_input=euro_input
    )

    @app.url_defaults
    def static_version(endpoint, values):
        """Hängt an statische Dateien ?v=<Änderungszeit> an, damit Browser nach Änderungen
        nicht die alte Fassung aus dem Cache nehmen."""
        if endpoint != "static" or "v" in values or "filename" not in values:
            return
        try:
            values["v"] = int(os.stat(os.path.join(app.static_folder, values["filename"])).st_mtime)
        except OSError:
            pass

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return resp
