"""Admin-Bereich unter /admin. Zugriffsschutz per Basic Auth im nginx-Ingress (siehe README)."""
import csv
import io
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   send_file, send_from_directory, url_for)

from . import card, logic, mailer
from .db import get_db
from .settings import DEFAULTS, as_int, get_all, localize, save
from .util import (BERLIN, EMAIL_RE, ImageError, bild_namen, bild_urls, delete_upload, euro_input, fmt_dt, fmt_euro,
                   in_days_iso, new_token, now_iso, parse_euro, save_mail_image, save_runner_image,
                   save_sponsor_image, used_placeholders)

bp = Blueprint("admin", __name__, url_prefix="/admin")

ZAHLARTEN = {"paypal": "PayPal", "bar": "bar", "ueberweisung": "Überweisung"}
TEMPLATES = [
    ("confirm", "Bestätigungsmail", "nach der Registrierung, enthält {bestaetigungslink}"),
    ("already", "Schon dabei", "bei erneuter Registrierung einer bestätigten Adresse"),
    ("welcome", "Willkommen", "optional, wenn der Admin einen Sponsor anlegt"),
    ("training", "Rundmail: Training", "Mustervorlage für die Rundmail"),
    ("reminder", "Rundmail: Erinnerung am Lauftag", "Mustervorlage für die Rundmail"),
    ("plaetze", "Rundmail: Auf die Plätze", "Mustervorlage für die Rundmail, wenn die Läufer an den Start gehen"),
    ("start", "Start", "geht beim Start des Laufs an alle bestätigten Sponsoren, wenn unten angehakt"),
    ("vorlaeufig", "Vorläufiges Ergebnis",
     "geht nach Ende des Laufs an alle bestätigten Sponsoren, wenn unten angehakt"),
    ("result", "Rundmail: Ergebnis und Zahlung", "Mustervorlage für die Rundmail"),
]


def ctx(**extra):
    s = get_all()
    data = {
        "s": s,
        "mode": logic.mode(s),
        "laeufer": logic.laeufer(s),
        "marke": logic.marke(s),
        "st": logic.stats(get_db(), s),
        "admin_email": current_app.config["ADMIN_EMAIL"],
        "zahlarten": ZAHLARTEN,
    }
    data.update(extra)
    return data


def get_sponsor(sid):
    sp = get_db().execute("SELECT * FROM sponsor WHERE id = ?", (sid,)).fetchone()
    if sp is None:
        abort(404)
    return sp


# ---------------------------------------------------------------- Übersicht

@bp.route("/")
def dashboard():
    s = get_all()
    warnings = []
    if not s.get("smtp_password"):
        warnings.append(("Kein SMTP-Passwort eingetragen – es werden keine Mails verschickt.", "admin.mail_settings"))
    if not current_app.config["ADMIN_EMAIL"]:
        warnings.append(("ADMIN_EMAIL fehlt in der .env – Testmails sind nicht möglich.", None))
    if "[" in s.get("impressum", ""):
        warnings.append(("Im Impressum steht noch ein Platzhalter in eckigen Klammern.", "admin.settings_page"))
    if current_app.config["SECRET_KEY"].startswith("dev-"):
        warnings.append(("SECRET_KEY in der .env ist noch der Entwicklungswert.", None))
    recent = get_db().execute("SELECT * FROM sponsor ORDER BY erstellt_am DESC LIMIT 5").fetchall()
    return render_template("admin/dashboard.html", **ctx(warnings=warnings, recent=recent))


# ---------------------------------------------------------------- Sponsoren

@bp.route("/sponsoren")
def sponsors():
    s = get_all()
    status = request.args.get("status", "alle")
    zahlung = request.args.get("zahlung", "alle")
    where, args = [], []
    if status in ("bestaetigt", "unbestaetigt"):
        where.append("status = ?")
        args.append(status)
    if zahlung == "offen":
        where.append("bezahlt_am IS NULL AND status = 'bestaetigt'")
    elif zahlung == "bezahlt":
        where.append("bezahlt_am IS NOT NULL")
    sql = "SELECT * FROM sponsor" + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {logic.ORDER}"
    runden = as_int(s, "runden")
    rows = [{"sp": r, "erloes": logic.erloes_cent(r, runden)} for r in get_db().execute(sql, args)]
    return render_template("admin/sponsors.html", **ctx(rows=rows, status=status, zahlung=zahlung))


def read_sponsor_form(form, files, existing=None):
    errors, data = {}, {}
    data["name"] = (form.get("name") or "").strip()
    if not 1 <= len(data["name"]) <= 80:
        errors["name"] = "Name fehlt oder ist zu lang."
    email = (form.get("email") or "").strip().lower()
    if email and not EMAIL_RE.match(email):
        errors["email"] = "E-Mail-Adresse ist ungültig."
    if email:
        dup = get_db().execute("SELECT id FROM sponsor WHERE email = ?", (email,)).fetchone()
        if dup and (existing is None or dup["id"] != existing["id"]):
            errors["email"] = "Diese E-Mail-Adresse ist schon eingetragen."
    data["email"] = email or None
    try:
        data["betrag_cent"] = parse_euro(form.get("betrag"))
        if data["betrag_cent"] <= 0:
            errors["betrag"] = "Betrag muss größer als 0 sein."
    except ValueError:
        errors["betrag"] = "Betrag ungültig (z. B. 1,50)."
    cap = (form.get("hoechst") or "").strip()
    try:
        data["hoechst_cent"] = parse_euro(cap) if cap else None
    except ValueError:
        errors["hoechst"] = "Höchstbetrag ungültig."
    data["anonym"] = 1 if form.get("anonym") else 0
    data["quittung"] = 1 if form.get("quittung") else 0
    data["sprache"] = "en" if form.get("sprache") == "en" else "de"
    for key in ("quittung_name", "strasse", "plz_ort"):
        data[key] = (form.get(key) or "").strip()[:120]
    data["notiz"] = (form.get("notiz") or "").strip()[:1000]
    upload = files.get("bild")
    data["_upload"] = upload if upload and upload.filename else None
    data["_bild_entfernen"] = bool(form.get("bild_entfernen"))
    return data, errors


@bp.route("/sponsoren/neu", methods=["GET", "POST"])
def sponsor_new():
    if request.method == "POST":
        data, errors = read_sponsor_form(request.form, request.files)
        if not errors and data["_upload"]:
            try:
                data["bild"] = save_sponsor_image(data["_upload"])
            except ImageError as exc:
                errors["bild"] = str(exc)
        if errors:
            return render_template("admin/sponsor_form.html", **ctx(sp=None, form=request.form, errors=errors)), 400
        fields = {k: v for k, v in data.items() if not k.startswith("_")}
        fields.update(status="bestaetigt", bestaetigt_am=now_iso(), bestaetigt_durch="admin",
                      quelle="admin", erstellt_am=now_iso())
        db = get_db()
        cols = ", ".join(fields)
        sid = db.execute(f"INSERT INTO sponsor ({cols}) VALUES ({', '.join('?' for _ in fields)})",
                         tuple(fields.values())).lastrowid
        db.commit()
        if request.form.get("willkommen") and fields.get("email"):
            sp = get_sponsor(sid)
            lang = sp["sprache"]
            s = localize(get_all(), lang)
            mailer.send_async(sp["email"], *logic.render_template_pair(
                s, "welcome", logic.sponsor_ctx(sp, s, logic.stats(db, s), lang=lang)))
            flash("Sponsor angelegt, Willkommensmail wird gesendet.", "ok")
        else:
            flash("Sponsor angelegt.", "ok")
        return redirect(url_for("admin.sponsors"))
    return render_template("admin/sponsor_form.html", **ctx(sp=None, form={}, errors={}))


@bp.route("/sponsoren/<int:sid>", methods=["GET", "POST"])
def sponsor_edit(sid):
    sp = get_sponsor(sid)
    if request.method == "POST":
        data, errors = read_sponsor_form(request.form, request.files, existing=sp)
        if not errors and data["_upload"]:
            try:
                data["bild"] = save_sponsor_image(data["_upload"])
                delete_upload(sp["bild"])
            except ImageError as exc:
                errors["bild"] = str(exc)
        elif not errors and data["_bild_entfernen"]:
            delete_upload(sp["bild"])
            data["bild"] = None
        if errors:
            return render_template("admin/sponsor_form.html", **ctx(sp=sp, form=request.form, errors=errors)), 400
        fields = {k: v for k, v in data.items() if not k.startswith("_")}
        db = get_db()
        db.execute(f"UPDATE sponsor SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                   (*fields.values(), sid))
        db.commit()
        flash("Änderungen gespeichert.", "ok")
        return redirect(url_for("admin.sponsors"))
    form = dict(sp)
    form["betrag"] = euro_input(sp["betrag_cent"])
    form["hoechst"] = euro_input(sp["hoechst_cent"])
    return render_template("admin/sponsor_form.html", **ctx(sp=sp, form=form, errors={}))


@bp.route("/sponsoren/<int:sid>/bestaetigen", methods=["POST"])
def sponsor_confirm(sid):
    get_sponsor(sid)
    db = get_db()
    db.execute("UPDATE sponsor SET status='bestaetigt', bestaetigt_am=?, bestaetigt_durch='admin', token_hash=NULL "
               "WHERE id=?", (now_iso(), sid))
    db.commit()
    flash("Sponsor bestätigt.", "ok")
    return redirect(request.referrer or url_for("admin.sponsors"))


@bp.route("/sponsoren/<int:sid>/link-senden", methods=["POST"])
def sponsor_resend(sid):
    sp = get_sponsor(sid)
    if not sp["email"] or sp["status"] == "bestaetigt":
        flash("Für diesen Sponsor ist kein Bestätigungslink nötig.", "warn")
        return redirect(url_for("admin.sponsors"))
    token, token_hash = new_token()
    db = get_db()
    db.execute("UPDATE sponsor SET token_hash=?, token_ablauf=? WHERE id=?", (token_hash, in_days_iso(7), sid))
    db.commit()
    from .public import send_confirm_mail

    send_confirm_mail(sp, token)
    flash(f"Bestätigungslink an {sp['email']} wird gesendet.", "ok")
    return redirect(request.referrer or url_for("admin.sponsors"))


@bp.route("/sponsoren/<int:sid>/loeschen", methods=["POST"])
def sponsor_delete(sid):
    sp = get_sponsor(sid)
    delete_upload(sp["bild"])
    db = get_db()
    db.execute("DELETE FROM sponsor WHERE id = ?", (sid,))
    db.commit()
    flash(f"{sp['name']} wurde gelöscht.", "ok")
    return redirect(url_for("admin.sponsors"))


@bp.route("/sponsoren/<int:sid>/zahlung", methods=["POST"])
def sponsor_payment(sid):
    get_sponsor(sid)
    db = get_db()
    zahlart = request.form.get("zahlart", "")
    if zahlart == "offen":
        db.execute("UPDATE sponsor SET bezahlt_am=NULL, zahlart=NULL WHERE id=?", (sid,))
        flash("Als offen markiert.", "ok")
    elif zahlart in ZAHLARTEN:
        db.execute("UPDATE sponsor SET bezahlt_am=?, zahlart=? WHERE id=?", (now_iso(), zahlart, sid))
        flash(f"Als bezahlt markiert ({ZAHLARTEN[zahlart]}).", "ok")
    db.commit()
    return redirect(request.referrer or url_for("admin.sponsors"))


@bp.route("/bild/<name>")
def bild(name):
    if "/" in name:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_DIR"], name)


# ---------------------------------------------------------------- Lauf und Ergebnis

def send_start_mail():
    """Beim Start: Vorlage „Start“ als Rundmail an alle bestätigten Sponsoren, wenn eingeschaltet."""
    s = get_all()
    if s.get("start_mail_aktiv") != "1":
        return
    rcpt = recipients(False)
    if not rcpt:
        flash("Start-Mail: keine Empfänger.", "warn")
        return
    create_rundmail(s["tpl_start_subject"], s["tpl_start_body"], s["tpl_start_subject_en"], s["tpl_start_body_en"],
                    s.get("tpl_start_bilder", ""), rcpt)
    flash(f"Start-Mail an {len(rcpt)} Sponsoren wird gesendet (Protokoll unter Rundmail).", "ok")


def send_ende_mail(notify=True, sofort=False):
    """Nach Ende des Laufs: Vorlage „Vorläufiges Ergebnis“ als Rundmail an alle bestätigten Sponsoren,
    wenn eingeschaltet und die Laufuhr samt Karenzzeit abgelaufen ist. Höchstens einmal pro Start.
    Wird von /admin/lauf und den öffentlichen Seiten (Live-Abfrage) aufgerufen; notify=False ohne Flash.
    sofort=True (Button „Endzeit und vorläufige Rundenzahl speichern“) wartet nicht auf die Laufuhr."""
    s = get_all()
    if not (logic.ende_mail_manuell_moeglich(s) if sofort else logic.ende_mail_faellig(s)):
        return
    db = get_db()
    # Atomar markieren, damit gleichzeitige Anfragen nicht doppelt versenden
    cur = db.execute("UPDATE einstellung SET value=? WHERE key='ende_mail_gesendet_am' AND value=''",
                     (now_iso(),))
    db.commit()
    g.pop("settings", None)
    if cur.rowcount != 1:
        return
    rcpt = recipients(False)
    if not rcpt:
        if notify:
            flash("Mail „Vorläufiges Ergebnis“: keine Empfänger.", "warn")
        return
    create_rundmail(s["tpl_vorlaeufig_subject"], s["tpl_vorlaeufig_body"], s["tpl_vorlaeufig_subject_en"],
                    s["tpl_vorlaeufig_body_en"], s.get("tpl_vorlaeufig_bilder", ""), rcpt)
    if notify:
        flash(f"Lauf beendet – Mail „Vorläufiges Ergebnis“ an {len(rcpt)} Sponsoren wird gesendet "
              "(Protokoll unter Rundmail).", "ok")


@bp.route("/lauf", methods=["GET", "POST"])
def race():
    s = get_all()
    db = get_db()
    if request.method == "GET":
        send_ende_mail()
        s = get_all()
    if request.method == "POST":
        action = request.form.get("action")
        alt = as_int(s, "runden")
        neu = alt
        if action == "plus":
            neu = alt + 1
        elif action == "minus":
            neu = max(0, alt - 1)
        elif action == "runden":
            try:
                neu = max(0, int(request.form.get("runden", alt)))
            except ValueError:
                flash("Bitte eine ganze Zahl eingeben.", "warn")
        elif action == "phase":
            updates = {
                "phase": "ergebnis" if request.form.get("phase") == "ergebnis" else "sammeln",
                "live_aktiv": "1" if request.form.get("live_aktiv") else "0",
            }
            # Wechsel in die Live-Phase startet die Laufuhr, falls noch nicht gestartet
            if updates["live_aktiv"] == "1" and s.get("live_aktiv") != "1" and not s.get("lauf_gestartet_am"):
                updates["lauf_gestartet_am"] = now_iso()
                updates["ende_mail_gesendet_am"] = ""
            save(updates)
            flash("Phase gespeichert." + (" Laufuhr gestartet." if "lauf_gestartet_am" in updates else ""), "ok")
            if "lauf_gestartet_am" in updates:
                send_start_mail()
        elif action == "start":
            if s.get("lauf_gestartet_am"):
                flash("Der Lauf ist schon gestartet.", "warn")
            else:
                save({"lauf_gestartet_am": now_iso(), "live_aktiv": "1", "ende_mail_gesendet_am": "", "ende_zeit": ""})
                flash("Lauf gestartet – die Laufuhr läuft, Live-Zählung ist an.", "ok")
                send_start_mail()
        elif action == "start_reset":
            save({"lauf_gestartet_am": "", "ende_mail_gesendet_am": "", "ende_zeit": ""})
            flash("Start zurückgesetzt.", "ok")
        elif action == "uhr":
            updates = {"countdown_aktiv": "1" if request.form.get("countdown_aktiv") else "0"}
            start = (request.form.get("start_zeit") or "").strip()[:16]
            if logic.start_zeit({"start_zeit": start}):
                updates["start_zeit"] = start
            else:
                flash("Startzeit ungültig – unverändert gelassen.", "warn")
            try:
                dauer = int(request.form.get("dauer_min") or 0) * 60 + int(request.form.get("dauer_sek") or 0)
                if dauer < 1:
                    raise ValueError
                updates["laufdauer_s"] = str(dauer)
            except ValueError:
                flash("Laufdauer ungültig – unverändert gelassen.", "warn")
            save(updates)
            flash("Startzeit gespeichert.", "ok")
        elif action == "ende":
            ende = (request.form.get("ende_zeit") or "").strip()[:16]
            if not logic.ortszeit(ende):
                if ende:
                    flash("Endzeit ungültig – stattdessen die aktuelle Uhrzeit genommen.", "warn")
                ende = datetime.now(BERLIN).strftime("%Y-%m-%dT%H:%M")
            try:
                neu = max(0, int(request.form.get("runden", alt)))
            except ValueError:
                flash("Rundenzahl ungültig – unverändert gelassen.", "warn")
            save({"ende_zeit": ende})
            flash(f"Endzeit {logic.ortszeit(ende).strftime('%d.%m.%Y %H:%M')} und vorläufige Rundenzahl {neu} "
                  "gespeichert.", "ok")
        elif action == "absage":
            save({
                "abgesagt": "1" if request.form.get("abgesagt") else "0",
                "absage_text": request.form.get("absage_text", "").strip(),
                "absage_text_en": request.form.get("absage_text_en", "").strip(),
            })
            flash("Absage-Einstellung gespeichert.", "ok")
        if neu != alt:
            save({"runden": neu})
            db.execute("INSERT INTO runden_protokoll(zeit, alt, neu) VALUES (?,?,?)", (now_iso(), alt, neu))
            db.commit()
            if action == "runden":
                flash(f"Rundenzahl auf {neu} gesetzt.", "ok")
        if action == "ende":
            s = get_all()
            if s.get("ende_mail_aktiv") != "1":
                flash("Mail „Vorläufiges Ergebnis“ ist ausgeschaltet (Mail-Einstellungen) – keine Mail gesendet.",
                      "warn")
            elif s.get("ende_mail_gesendet_am"):
                flash(f"Mail „Vorläufiges Ergebnis“ wurde schon um {fmt_dt(s['ende_mail_gesendet_am'])} "
                      "angestoßen – nicht erneut gesendet.", "warn")
            else:
                send_ende_mail(sofort=True)
        return redirect(url_for("admin.race"))
    log = db.execute("SELECT * FROM runden_protokoll ORDER BY id DESC LIMIT 30").fetchall()
    dauer = as_int(s, "laufdauer_s", 600)
    return render_template("admin/race.html", **ctx(log=log, clock=logic.clock(s), lauf_start=logic.lauf_start(s),
                                                     dauer_min=dauer // 60, dauer_sek=dauer % 60,
                                                     ende_mail_ms=logic.ende_mail_zeitpunkt_ms(s),
                                                     ende=logic.ortszeit(s.get("ende_zeit"))))


# ---------------------------------------------------------------- Einstellungen

SETTING_FIELDS = ["laeufer_name", "karten_name", "klasse", "schule", "lauf_datum", "rundenlaenge_m",
                  "marke", "headline", "intro", "zweck", "ablauf_text", "footer_text", "hoechst_faktor",
                  "sponsor_sort_feld", "sponsor_sort_richtung", "sponsor_pro_seite",
                  "paypal_empfaenger", "paypal_me", "impressum", "datenschutz",
                  "marke_en", "headline_en", "intro_en", "zweck_en", "ablauf_text_en", "footer_text_en",
                  "impressum_en", "datenschutz_en"]


@bp.route("/einstellungen", methods=["GET", "POST"])
def settings_page():
    s = get_all()
    if request.method == "POST":
        updates = {k: request.form.get(k, "").strip() for k in SETTING_FIELDS if k in request.form}
        updates["bestaetigungsseite"] = "1" if request.form.get("bestaetigungsseite") else "0"
        updates["sponsor_zeige_zeitpunkt"] = "1" if request.form.get("sponsor_zeige_zeitpunkt") else "0"
        try:
            updates["rundenlaenge_m"] = str(max(1, int(updates.get("rundenlaenge_m") or 100)))
        except ValueError:
            flash("Rundenlänge bitte als ganze Zahl in Metern.", "warn")
            updates.pop("rundenlaenge_m", None)
        try:
            updates["max_betrag_cent"] = str(parse_euro(request.form.get("max_betrag") or "100"))
        except ValueError:
            flash("Obergrenze pro Runde ungültig – unverändert gelassen.", "warn")
        try:
            updates["mindestbeitrag_cent"] = str(parse_euro(request.form.get("mindestbeitrag") or "0"))
        except ValueError:
            flash("Mindestbetrag pro Runde ungültig – unverändert gelassen.", "warn")
        if updates.get("sponsor_sort_feld") not in ("name", "datum", "betrag"):
            updates.pop("sponsor_sort_feld", None)
        if updates.get("sponsor_sort_richtung") not in ("auf", "ab"):
            updates.pop("sponsor_sort_richtung", None)
        if updates.get("sponsor_pro_seite") not in ("0", "5", "10", "25", "50", "100"):
            updates.pop("sponsor_pro_seite", None)
        upload = request.files.get("laeufer_bild")
        if request.form.get("bild_zuruecksetzen"):
            delete_upload(s.get("laeufer_bild"))
            updates["laeufer_bild"] = ""
        elif upload and upload.filename:
            try:
                name = save_runner_image(upload)
                delete_upload(s.get("laeufer_bild"))
                updates["laeufer_bild"] = name
            except ImageError as exc:
                flash(str(exc), "warn")
        save(updates)
        flash("Einstellungen gespeichert.", "ok")
        return redirect(url_for("admin.settings_page"))
    return render_template("admin/settings.html", **ctx())


SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_security", "smtp_user", "mail_from", "mail_from_name",
             "mail_reply_to", "mail_rate_seconds"]


def wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def smtp_form_values():
    """Mailserver-Werte aus dem Formular. Ein leeres Passwortfeld behält das gespeicherte."""
    updates = {k: request.form.get(k, "").strip() for k in SMTP_KEYS}
    if updates["smtp_security"] not in ("starttls", "ssl", "none"):
        updates["smtp_security"] = "starttls"
    try:
        port = int(updates["smtp_port"])
        if not 0 < port < 65536:
            raise ValueError
    except ValueError:
        return updates, "Der Port muss eine Zahl zwischen 1 und 65535 sein."
    updates["mail_rate_seconds"] = updates["mail_rate_seconds"].replace(",", ".") or "0"
    try:
        if float(updates["mail_rate_seconds"]) < 0:
            raise ValueError
    except ValueError:
        return updates, "Die Pause zwischen Rundmails muss eine Zahl ab 0 sein."
    if not updates["smtp_host"]:
        return updates, "Bitte einen SMTP-Server eintragen."
    for key in ("mail_from", "mail_reply_to"):
        if updates[key] and not EMAIL_RE.match(updates[key]):
            return updates, "Absender- oder Antwortadresse ist ungültig."
    if request.form.get("smtp_password"):
        updates["smtp_password"] = request.form["smtp_password"]
    return updates, None


def smtp_reply(ok, message, log=None):
    if wants_json():
        saved = get_all()
        return {"ok": ok, "message": message, "log": log or [], "password_saved": bool(saved.get("smtp_password")),
                "smtp_port": saved.get("smtp_port"), "smtp_security": saved.get("smtp_security")}
    flash(message, "ok" if ok else "warn")
    if log:
        return render_template("admin/mail_settings.html",
                               **ctx(templates=TEMPLATES, placeholders=logic.PLACEHOLDER_HELP, smtp_log=log))
    return redirect(url_for("admin.mail_settings"))


@bp.route("/mail-einstellungen", methods=["GET", "POST"])
def mail_settings():
    if request.method == "POST":
        updates = {}
        for key, _label, _hint in TEMPLATES:
            updates[f"tpl_{key}_subject"] = request.form.get(f"tpl_{key}_subject", "").strip()
            updates[f"tpl_{key}_body"] = request.form.get(f"tpl_{key}_body", "").replace("\r\n", "\n").strip()
            updates[f"tpl_{key}_subject_en"] = request.form.get(f"tpl_{key}_subject_en", "").strip()
            updates[f"tpl_{key}_body_en"] = request.form.get(f"tpl_{key}_body_en", "").replace("\r\n", "\n").strip()
        for key in [k for k in updates if not updates[k]]:
            updates[key] = DEFAULTS[key]  # leere Vorlage = Standard wiederherstellen
        s = get_all()
        for key, _label, _hint in TEMPLATES:
            bilder, fehler = update_bilder(s.get(f"tpl_{key}_bilder", ""), f"tpl_{key}_bild_weg",
                                           f"tpl_{key}_bild_neu")
            updates[f"tpl_{key}_bilder"] = bilder
            for msg in fehler:
                flash(msg, "warn")
        if request.form.get("start_mail_formular"):
            updates["start_mail_aktiv"] = "1" if request.form.get("start_mail_aktiv") else "0"
            updates["ende_mail_aktiv"] = "1" if request.form.get("ende_mail_aktiv") else "0"
        save(updates)
        flash("Vorlagen gespeichert.", "ok")
        return redirect(url_for("admin.mail_settings"))
    return render_template("admin/mail_settings.html",
                           **ctx(templates=TEMPLATES, placeholders=logic.PLACEHOLDER_HELP))


def update_bilder(value, weg_feld, neu_feld):
    """Bildliste einer Vorlage oder Rundmail: angehakte entfernen, hochgeladene anhängen.
    Die Dateien bleiben liegen, weil schon verschickte Mails auf sie verlinken."""
    weg = set(request.form.getlist(weg_feld))
    namen = [n for n in bild_namen(value) if n not in weg]
    fehler = []
    for upload in request.files.getlist(neu_feld):
        if not upload or not upload.filename:
            continue
        try:
            namen.append(save_mail_image(upload))
        except ImageError as exc:
            fehler.append(f"{upload.filename}: {exc}")
    return "\n".join(namen), fehler


@bp.route("/mailserver", methods=["POST"])
def smtp_save():
    updates, error = smtp_form_values()
    if error:
        return smtp_reply(False, error)
    save(updates)
    return smtp_reply(True, "Mailserver-Einstellungen gespeichert.")


def run_smtp_test(send_mail):
    """Testet die Werte aus dem Formular, auch wenn sie noch nicht gespeichert sind.
    Klappt die Verbindung, werden sie samt funktionierender Port-Variante gespeichert."""
    updates, error = smtp_form_values()
    if error:
        return smtp_reply(False, error)
    to = None
    if send_mail:
        to = (request.form.get("test_to") or "").strip()
        if not to:
            return smtp_reply(False, "Bitte eine Adresse für die Testmail eintragen.")
        if not EMAIL_RE.match(to):
            return smtp_reply(False, "Die Adresse für die Testmail ist ungültig.")
    cfg = {**get_all(), **updates}
    variant, log = mailer.smtp_test(cfg, to)
    for line in log:
        current_app.logger.warning("SMTP-Test: %s", line)
    if not variant:
        what = "Testmail konnte nicht gesendet werden" if to else "Keine Verbindung zum Mailserver möglich"
        return smtp_reply(False, f"{what}. Nichts gespeichert – Details im Protokoll.", log)
    updates.update(smtp_port=str(variant[0]), smtp_security=variant[1])
    save(updates)
    done = f"Testmail an {to} gesendet" if to else "Verbindung und Anmeldung erfolgreich"
    return smtp_reply(True, f"{done} (Port {variant[0]}, {variant[1].upper()}). Einstellungen gespeichert.", log)


@bp.route("/smtp-test", methods=["POST"])
def smtp_test():
    return run_smtp_test(send_mail=False)


@bp.route("/testmail", methods=["POST"])
def smtp_testmail():
    return run_smtp_test(send_mail=True)


# ---------------------------------------------------------------- Rundmail

def recipients(include_unconfirmed):
    sql = "SELECT * FROM sponsor WHERE email IS NOT NULL AND email != ''"
    if not include_unconfirmed:
        sql += " AND status = 'bestaetigt'"
    return get_db().execute(sql + f" ORDER BY {logic.ORDER}").fetchall()


def create_rundmail(betreff, text, betreff_en, text_en, bilder, rcpt):
    db = get_db()
    rid = db.execute(
        "INSERT INTO rundmail(betreff, text, betreff_en, text_en, bilder, erstellt_am) VALUES (?,?,?,?,?,?)",
        (betreff, text, betreff_en, text_en, bilder, now_iso()),
    ).lastrowid
    db.executemany(
        "INSERT INTO rundmail_empfaenger(rundmail_id, sponsor_id, email) VALUES (?,?,?)",
        [(rid, r["id"], r["email"]) for r in rcpt],
    )
    db.commit()
    mailer.start_rundmail(rid)
    return rid


@bp.route("/rundmail", methods=["GET", "POST"])
def rundmail():
    s = get_all()
    db = get_db()
    st = logic.stats(db, s)
    form = {"betreff": "", "text": "", "betreff_en": "", "text_en": "", "sponsor_id": "", "unbestaetigte": "",
            "bilder": ""}
    preview, warn = None, None
    if request.method == "POST":
        form.update({k: request.form.get(k, "") for k in form})
        form["text"] = form["text"].replace("\r\n", "\n")
        form["text_en"] = form["text_en"].replace("\r\n", "\n")
        action = request.form.get("action")
        form["bilder"], fehler = update_bilder(form["bilder"], "bild_weg", "bild_neu")
        for msg in fehler:
            flash(msg, "warn")
        if action in ("vorlage_training", "vorlage_reminder", "vorlage_plaetze", "vorlage_start",
                      "vorlage_vorlaeufig", "vorlage_result"):
            key = action.split("_", 1)[1]
            form["betreff"], form["text"] = s[f"tpl_{key}_subject"], s[f"tpl_{key}_body"]
            form["betreff_en"], form["text_en"] = s[f"tpl_{key}_subject_en"], s[f"tpl_{key}_body_en"]
            form["bilder"] = s.get(f"tpl_{key}_bilder", "")
        all_rcpt = recipients(bool(form["unbestaetigte"]))
        chosen = next((r for r in all_rcpt if str(r["id"]) == form["sponsor_id"]), all_rcpt[0] if all_rcpt else None)
        used = used_placeholders(form["betreff"] + form["text"] + form["betreff_en"] + form["text_en"])
        if st["runden"] == 0 and used & logic.RESULT_PLACEHOLDERS:
            warn = "Die Vorlage nutzt Ergebnis-Platzhalter, aber es sind noch 0 Runden eingetragen."
        if chosen and form["text"]:
            lang = chosen["sprache"] if chosen["sprache"] == "en" and form["text_en"].strip() else "de"
            betreff, text = (form["betreff_en"], form["text_en"]) if lang == "en" else (form["betreff"], form["text"])
            c = logic.sponsor_ctx(chosen, s, st, lang=lang)
            from .util import render_placeholders

            preview = {"to": chosen["email"], "lang": lang, "betreff": render_placeholders(betreff, c),
                       "text": render_placeholders(text, c), "bilder": bild_urls(form["bilder"])}
        if action == "test":
            to = current_app.config["ADMIN_EMAIL"]
            if not to:
                flash("ADMIN_EMAIL fehlt in der .env.", "warn")
            elif not preview:
                flash("Für die Testmail braucht es einen Text und mindestens einen Empfänger.", "warn")
            else:
                try:
                    mailer.send(to, "[Test] " + preview["betreff"], preview["text"], s, images=preview["bilder"])
                    flash(f"Testmail an {to} gesendet.", "ok")
                except mailer.MailError as exc:
                    flash(str(exc), "warn")
        elif action == "senden":
            if not form["betreff"].strip() or not form["text"].strip():
                flash("Betreff und Text dürfen nicht leer sein.", "warn")
            elif not all_rcpt:
                flash("Es gibt keine Empfänger.", "warn")
            elif warn and not request.form.get("trotzdem"):
                flash(warn + " Zum Senden „trotzdem senden“ ankreuzen.", "warn")
            elif request.form.get("anzahl") != str(len(all_rcpt)):
                flash("Bitte die Empfängerzahl zur Bestätigung eintragen.", "warn")
            else:
                rid = create_rundmail(form["betreff"], form["text"], form["betreff_en"], form["text_en"],
                                      form["bilder"], all_rcpt)
                flash(f"Versand an {len(all_rcpt)} Empfänger gestartet.", "ok")
                return redirect(url_for("admin.rundmail_log", rid=rid))
    all_rcpt = recipients(bool(form["unbestaetigte"]))
    history = db.execute(
        "SELECT r.*, (SELECT COUNT(*) FROM rundmail_empfaenger e WHERE e.rundmail_id=r.id) AS anzahl, "
        "(SELECT COUNT(*) FROM rundmail_empfaenger e WHERE e.rundmail_id=r.id AND e.status='gesendet') AS ok "
        "FROM rundmail r ORDER BY r.id DESC"
    ).fetchall()
    return render_template("admin/rundmail.html", **ctx(form=form, preview=preview, warn=warn, rcpt=all_rcpt,
                                                        history=history, placeholders=logic.PLACEHOLDER_HELP))


@bp.route("/rundmail/<int:rid>")
def rundmail_log(rid):
    db = get_db()
    mail = db.execute("SELECT * FROM rundmail WHERE id=?", (rid,)).fetchone() or abort(404)
    rows = db.execute(
        "SELECT e.*, s.name FROM rundmail_empfaenger e LEFT JOIN sponsor s ON s.id = e.sponsor_id "
        "WHERE rundmail_id=? ORDER BY e.id", (rid,)
    ).fetchall()
    return render_template("admin/rundmail_log.html", **ctx(mail=mail, rows=rows))


@bp.route("/rundmail/<int:rid>/wiederholen", methods=["POST"])
def rundmail_retry(rid):
    db = get_db()
    n = db.execute("SELECT COUNT(*) FROM rundmail_empfaenger WHERE rundmail_id=? AND status='fehler'",
                   (rid,)).fetchone()[0]
    if n:
        db.execute("UPDATE rundmail_empfaenger SET status='wartet' WHERE rundmail_id=? AND status='fehler'", (rid,))
        db.commit()
        mailer.start_rundmail(rid)
        flash(f"{n} fehlgeschlagene Mails werden erneut gesendet.", "ok")
    return redirect(url_for("admin.rundmail_log", rid=rid))


# ---------------------------------------------------------------- Karte, Export, Löschen

@bp.route("/karte")
def card_page():
    return render_template("admin/card.html", **ctx())


@bp.route("/karte.<fmt>")
def card_download(fmt):
    s = get_all()
    sponsors = logic.confirmed(get_db())
    result_known = s.get("phase") == "ergebnis" or as_int(s, "runden") > 0
    docx = card.build_docx(sponsors, s, result_known).getvalue()
    stem = f"Sponsorenkarte-{logic.laeufer(s)}"
    if fmt == "docx":
        return send_file(io.BytesIO(docx), as_attachment=True, download_name=f"{stem}.docx",
                         mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if fmt == "pdf":
        try:
            pdf = card.docx_to_pdf(docx, current_app.config["SOFFICE_BIN"])
        except Exception as exc:  # noqa: BLE001
            current_app.logger.exception("PDF-Export fehlgeschlagen")
            pdf = None
            flash(f"PDF-Export fehlgeschlagen: {exc}", "warn")
        if pdf is None:
            flash("PDF-Export nicht möglich (LibreOffice fehlt). Bitte die Word-Datei nutzen.", "warn")
            return redirect(url_for("admin.card_page"))
        return send_file(io.BytesIO(pdf), as_attachment=True, download_name=f"{stem}.pdf",
                         mimetype="application/pdf")
    abort(404)


@bp.route("/export.csv")
def export_csv():
    s = get_all()
    runden = as_int(s, "runden")
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Name", "E-Mail", "Anonym", "Betrag pro Runde", "Höchstbetrag", "Spende", "Status",
                "bestätigt am", "bestätigt durch", "bezahlt am", "Zahlart", "Quittung", "Quittung Name",
                "Straße", "PLZ Ort", "Notiz"])
    for r in get_db().execute(f"SELECT * FROM sponsor ORDER BY {logic.ORDER}"):
        w.writerow([r["name"], r["email"] or "", "ja" if r["anonym"] else "nein",
                    fmt_euro(r["betrag_cent"], False), fmt_euro(r["hoechst_cent"], False) if r["hoechst_cent"] else "",
                    fmt_euro(logic.erloes_cent(r, runden), False), r["status"], fmt_dt(r["bestaetigt_am"]),
                    r["bestaetigt_durch"] or "", fmt_dt(r["bezahlt_am"]), ZAHLARTEN.get(r["zahlart"] or "", ""),
                    "ja" if r["quittung"] else "nein", r["quittung_name"] or "", r["strasse"] or "",
                    r["plz_ort"] or "", r["notiz"] or ""])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=sponsoren.csv"})


@bp.route("/alle-daten-loeschen", methods=["POST"])
def delete_all():
    if request.form.get("bestaetigung") != "LÖSCHEN":
        flash("Zum Löschen bitte LÖSCHEN in Großbuchstaben eintragen.", "warn")
        return redirect(url_for("admin.card_page"))
    db = get_db()
    for r in db.execute("SELECT bild FROM sponsor WHERE bild IS NOT NULL").fetchall():
        delete_upload(r["bild"])
    db.execute("DELETE FROM rundmail_empfaenger")
    db.execute("DELETE FROM rundmail")
    db.execute("DELETE FROM sponsor")
    db.execute("DELETE FROM runden_protokoll")
    db.commit()
    flash("Alle Sponsordaten, Bilder und Rundmails wurden gelöscht.", "ok")
    return redirect(url_for("admin.dashboard"))
