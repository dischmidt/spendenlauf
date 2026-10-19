"""Öffentliche Seite: Startseite, Registrierung, Bestätigung per Link, Impressum, Datenschutz."""
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, g, redirect, render_template, request,
                   send_from_directory, url_for)

from . import logic, mailer
from .db import get_db
from .i18n import LANGS, t
from .settings import as_int, flag, get_all, localize
from .util import (EMAIL_RE, ImageError, client_ip, delete_upload, fmt_euro, hash_token, in_days_iso,
                   limiter, new_token, now_iso, parse_euro, parse_iso, render_og_image, save_sponsor_image)

bp = Blueprint("public", __name__)


def page_ctx(**extra):
    lang = getattr(g, "lang", "de")
    s = localize(get_all(), lang)
    db = get_db()
    ctx = {
        "s": s,
        "lang": lang,
        "mode": logic.mode(s),
        "laeufer": logic.laeufer(s),
        "marke": logic.marke(s),
        "headline": logic.headline(s),
        "footer_text": logic.footer_text(s),
        "st": logic.stats(db, s),
        "base_url": current_app.config["BASE_URL"],
        "clock": logic.clock(s),
    }
    if ctx["clock"] and "rest_s" in ctx["clock"]:
        ctx["clock"]["text"] = logic.fmt_rest(ctx["clock"]["rest_s"], t("clock.tage"))
    ctx.update(extra)
    return ctx


@bp.route("/sprache/<lang>")
def set_language(lang):
    if lang not in LANGS:
        abort(404)
    target = request.args.get("next", "/")
    if not target.startswith("/") or target.startswith("//"):
        target = "/"
    resp = redirect(target)
    resp.set_cookie(
        "lang", lang, max_age=60 * 60 * 24 * 365, samesite="Lax",
        secure=current_app.config["SESSION_COOKIE_SECURE"], httponly=True,
    )
    return resp


def sponsor_rows(s):
    runden = as_int(s, "runden")
    zeige_zeit = flag(s, "sponsor_zeige_zeitpunkt")
    mode = logic.mode(s)
    return [
        {
            "sp": sp,
            "erloes": logic.erloes_cent(sp, runden),
            "hoechst_mode": logic.hoechst_mode(sp, s),
            "zeitpunkt": logic.zeitpunkt_text(sp, mode) if zeige_zeit else None,
        }
        for sp in logic.confirmed(get_db(), s)
    ]


def _page_from_args():
    try:
        return max(1, int(request.args.get("seite", 1)))
    except ValueError:
        return 1


def paginated_rows(s):
    return paginate(sponsor_rows(s), s, _page_from_args())


def paginate(rows, s, page):
    pro_seite = as_int(s, "sponsor_pro_seite", 25)
    if pro_seite <= 0 or not rows:
        return rows, {"seite": 1, "seiten": 1, "aktiv": False}
    seiten = max(1, -(-len(rows) // pro_seite))
    seite = min(page, seiten)
    start = (seite - 1) * pro_seite
    return rows[start:start + pro_seite], {"seite": seite, "seiten": seiten, "aktiv": seiten > 1}


def check_ende_mail():
    """Lauf vorbei? Dann ggf. die Mail „Vorläufiges Ergebnis“ anstoßen. Die Live-Abfrage der
    Startseite (alle 15 Sekunden) sorgt dafür, dass das auch ohne offene Admin-Seite passiert."""
    from .admin import send_ende_mail

    try:
        send_ende_mail(notify=False)
    except Exception:  # noqa: BLE001 – die öffentliche Seite darf daran nicht scheitern
        current_app.logger.exception("Mail „Vorläufiges Ergebnis“ konnte nicht angestoßen werden")


@bp.route("/")
def index():
    check_ende_mail()
    s = get_all()
    rows, pager = paginated_rows(s)
    return render_template("index.html", **page_ctx(sponsors=rows, pager=pager, form={}, errors={}))


@bp.route("/teil/live")
def live_fragment():
    check_ende_mail()
    s = get_all()
    rows, pager = paginated_rows(s)
    return render_template("_live.html", **page_ctx(sponsors=rows, pager=pager))


def validate_registration(form, files, s):
    errors, data = {}, {}
    name = (form.get("name") or "").strip()
    if not 2 <= len(name) <= 80:
        errors["name"] = t("err.name")
    data["name"] = name

    email = (form.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 200:
        errors["email"] = t("err.email")
    data["email"] = email

    max_cent = as_int(s, "max_betrag_cent", 10000)
    min_cent = as_int(s, "mindestbeitrag_cent", 20)
    try:
        betrag = parse_euro(form.get("betrag"))
        if min_cent > 0 and betrag < min_cent:
            errors["betrag"] = t("err.betrag_min", betrag=fmt_euro(min_cent))
        elif betrag <= 0:
            errors["betrag"] = t("err.betrag_positive")
        elif betrag > max_cent:
            errors["betrag"] = t("err.betrag_max", betrag=fmt_euro(max_cent))
    except ValueError:
        betrag = None
        errors["betrag"] = t("err.betrag_format")
    data["betrag_cent"] = betrag

    raw_cap = (form.get("hoechst") or "").strip()
    cap = None
    if raw_cap:
        try:
            cap = parse_euro(raw_cap)
            if betrag and cap < betrag:
                errors["hoechst"] = t("err.hoechst_min")
        except ValueError:
            errors["hoechst"] = t("err.hoechst_format")
    data["hoechst_cent"] = cap or None

    data["anonym"] = 1 if form.get("anonym") else 0
    data["quittung"] = 1 if form.get("quittung") else 0
    data["quittung_name"] = (form.get("quittung_name") or "").strip()[:120]
    data["strasse"] = (form.get("strasse") or "").strip()[:120]
    data["plz_ort"] = (form.get("plz_ort") or "").strip()[:120]
    if data["quittung"]:
        if not data["quittung_name"]:
            errors["quittung_name"] = t("err.quittung_name")
        if not data["strasse"]:
            errors["strasse"] = t("err.strasse")
        if not data["plz_ort"]:
            errors["plz_ort"] = t("err.plz_ort")
    else:
        data["quittung_name"] = data["strasse"] = data["plz_ort"] = ""

    if not form.get("datenschutz"):
        errors["datenschutz"] = t("err.datenschutz")

    upload = files.get("bild")
    data["_upload"] = upload if (upload and upload.filename and not data["anonym"]) else None
    return data, errors


def confirm_link(token):
    return current_app.config["BASE_URL"] + url_for("public.confirm", token=token)


def send_confirm_mail(sp, token):
    lang = sp["sprache"] if sp["sprache"] in LANGS else "de"
    s = localize(get_all(), lang)
    ctx = logic.sponsor_ctx(sp, s, logic.stats(get_db(), s), {"bestaetigungslink": confirm_link(token)}, lang=lang)
    mailer.send_async(sp["email"], *logic.render_template_pair(s, "confirm", ctx))


@bp.route("/registrieren", methods=["POST"])
def register():
    s = get_all()
    if not logic.registration_open(s):
        return redirect(url_for("public.index"))
    if request.form.get("website"):  # Honeypot
        return render_template("message.html", **page_ctx(kind="check_mail"))
    if not limiter.hit(f"reg:{client_ip()}", 5, 3600):
        return render_template("message.html", **page_ctx(kind="too_many")), 429

    data, errors = validate_registration(request.form, request.files, s)
    data["sprache"] = g.lang
    if errors:
        rows, pager = paginated_rows(s)
        return render_template(
            "index.html", **page_ctx(sponsors=rows, pager=pager, form=request.form, errors=errors)
        ), 400

    db = get_db()
    existing = db.execute("SELECT * FROM sponsor WHERE email = ?", (data["email"],)).fetchone()
    if existing and existing["status"] == "bestaetigt":
        existing_lang = existing["sprache"] if existing["sprache"] in LANGS else "de"
        existing_s = localize(get_all(), existing_lang)
        ctx = logic.sponsor_ctx(existing, existing_s, logic.stats(db, existing_s), lang=existing_lang)
        mailer.send_async(existing["email"], *logic.render_template_pair(existing_s, "already", ctx))
        return render_template("message.html", **page_ctx(kind="check_mail"))

    bild = None
    if data["_upload"]:
        try:
            bild = save_sponsor_image(data["_upload"])
        except ImageError as exc:
            errors["bild"] = str(exc)
            rows, pager = paginated_rows(s)
            return render_template(
                "index.html", **page_ctx(sponsors=rows, pager=pager, form=request.form, errors=errors)
            ), 400

    token, token_hash = new_token()
    fields = {k: v for k, v in data.items() if not k.startswith("_")}
    fields.update(token_hash=token_hash, token_ablauf=in_days_iso(7))
    if existing:
        if bild and existing["bild"]:
            delete_upload(existing["bild"])
        fields["bild"] = bild or existing["bild"]
        sets = ", ".join(f"{k} = ?" for k in fields)
        db.execute(f"UPDATE sponsor SET {sets} WHERE id = ?", (*fields.values(), existing["id"]))
        sponsor_id = existing["id"]
    else:
        fields.update(bild=bild, status="unbestaetigt", quelle="web", erstellt_am=now_iso())
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        sponsor_id = db.execute(f"INSERT INTO sponsor ({cols}) VALUES ({marks})", tuple(fields.values())).lastrowid
    db.commit()

    sp = db.execute("SELECT * FROM sponsor WHERE id = ?", (sponsor_id,)).fetchone()
    send_confirm_mail(sp, token)
    return render_template("message.html", **page_ctx(kind="check_mail"))


def _sponsor_by_token(token):
    return get_db().execute("SELECT * FROM sponsor WHERE token_hash = ?", (hash_token(token),)).fetchone()


def _expired(sp):
    ablauf = parse_iso(sp["token_ablauf"])
    from datetime import datetime, timezone

    return ablauf is None or ablauf < datetime.now(timezone.utc)


@bp.route("/bestaetigen/<token>", methods=["GET", "POST"])
def confirm(token):
    sp = _sponsor_by_token(token)
    if sp is None:
        return render_template("message.html", **page_ctx(kind="invalid_link")), 404
    if sp["status"] == "bestaetigt":
        return render_template("message.html", **page_ctx(kind="already_confirmed", sponsor=sp))
    if _expired(sp):
        return render_template("message.html", **page_ctx(kind="expired", sponsor=sp)), 410
    if request.method == "GET" and flag(get_all(), "bestaetigungsseite"):
        # Nur wenn eingeschaltet: eigene Seite mit Klick, damit Link-Scanner von Mailprogrammen nichts auslösen.
        ctx = page_ctx(sponsor=sp, token=token)
        ctx["hoechst_mode"] = logic.hoechst_mode(sp, ctx["s"])
        return render_template("confirm.html", **ctx)
    db = get_db()
    db.execute(
        "UPDATE sponsor SET status='bestaetigt', bestaetigt_am=?, bestaetigt_durch='link', token_hash=NULL "
        "WHERE id=?",
        (now_iso(), sp["id"]),
    )
    db.commit()
    return render_template("message.html", **page_ctx(kind="confirmed", sponsor=sp))


@bp.route("/link-neu", methods=["POST"])
def resend():
    email = (request.form.get("email") or "").strip().lower()
    if not limiter.hit(f"resend:{client_ip()}", 5, 3600):
        return render_template("message.html", **page_ctx(kind="too_many")), 429
    db = get_db()
    sp = db.execute("SELECT * FROM sponsor WHERE email = ?", (email,)).fetchone()
    if sp and sp["status"] != "bestaetigt" and logic.registration_open(get_all()):
        token, token_hash = new_token()
        db.execute("UPDATE sponsor SET token_hash=?, token_ablauf=? WHERE id=?",
                   (token_hash, in_days_iso(7), sp["id"]))
        db.commit()
        send_confirm_mail(sp, token)
    return render_template("message.html", **page_ctx(kind="check_mail"))


@bp.route("/impressum")
def impressum():
    ctx = page_ctx(title=t("legal.impressum_title"))
    ctx["text"] = ctx["s"]["impressum"]
    return render_template("legal.html", **ctx)


@bp.route("/datenschutz")
def datenschutz():
    ctx = page_ctx(title=t("legal.datenschutz_title"))
    ctx["text"] = ctx["s"]["datenschutz"]
    return render_template("legal.html", **ctx)


@bp.route("/bild/<name>")
def bild(name):
    if "/" in name or not name.startswith(("s-", "m-")):
        abort(404)
    resp = send_from_directory(current_app.config["UPLOAD_DIR"], name, max_age=86400)
    return resp


def _laeufer_bild_path():
    name = get_all().get("laeufer_bild")
    if name and (Path(current_app.config["UPLOAD_DIR"]) / name).exists():
        return Path(current_app.config["UPLOAD_DIR"]) / name
    return Path(current_app.static_folder) / "img" / "laeufer-standard.png"


@bp.route("/laeufer-bild")
def laeufer_bild():
    path = _laeufer_bild_path()
    return send_from_directory(path.parent, path.name, max_age=300)


@bp.route("/og-bild")
def og_bild():
    data = render_og_image(_laeufer_bild_path())
    resp = Response(data, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@bp.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@bp.app_errorhandler(413)
def too_large(_e):
    return render_template("message.html", **page_ctx(kind="too_large")), 413


@bp.app_errorhandler(400)
def bad_request(e):
    return render_template("message.html", **page_ctx(kind="bad_request", detail=e.description)), 400
