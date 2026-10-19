"""Mailversand über SMTP (Einstellungen aus dem Admin-Bereich), Verbindungstest, Rundmail-Versand."""
import base64
import smtplib
import ssl
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from flask import current_app
from markupsafe import escape

from . import db as dbmod
from .settings import load
from .util import bild_urls, now_iso, text_to_html

VARIANTS = [(587, "starttls"), (465, "ssl")]


class MailError(Exception):
    pass


def _login(server, user, password):
    """smtplib kodiert AUTH nur als ASCII und scheitert an Umlauten oder € im Passwort
    mit einem UnicodeEncodeError. Dann AUTH PLAIN selbst mit UTF-8 schicken."""
    try:
        (user + password).encode("ascii")
    except UnicodeEncodeError:
        server.ehlo_or_helo_if_needed()
        if "plain" not in server.esmtp_features.get("auth", "").lower().split():
            raise MailError("Der Mailserver bietet kein AUTH PLAIN an – Passwort ohne Sonderzeichen nötig.")
        token = base64.b64encode(f"\0{user}\0{password}".encode("utf-8")).decode("ascii")
        code, resp = server.docmd("AUTH", "PLAIN " + token)
        if code != 235:
            raise smtplib.SMTPAuthenticationError(code, resp)
        return
    server.login(user, password)


def _connect(cfg, port=None, security=None):
    host = cfg.get("smtp_host", "").strip()
    port = int(port or cfg.get("smtp_port") or 587)
    security = security or cfg.get("smtp_security", "starttls")
    if not host:
        raise MailError("Kein SMTP-Server eingetragen.")
    ctx = ssl.create_default_context()
    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=20, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
    try:
        if security == "starttls":
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
        user = cfg.get("smtp_user", "").strip()
        if user:
            password = cfg.get("smtp_password", "")
            if not password:
                raise MailError("Kein SMTP-Passwort gespeichert.")
            _login(server, user, password)
    except BaseException:
        server.close()  # sonst bleibt die Verbindung bei falschem Passwort offen
        raise
    return server


def build_message(cfg, to, subject, body, images=None):
    msg = EmailMessage()
    sender = cfg.get("mail_from") or cfg.get("smtp_user")
    msg["From"] = formataddr((cfg.get("mail_from_name", ""), sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1] if "@" in sender else None)
    if cfg.get("mail_reply_to"):
        msg["Reply-To"] = cfg["mail_reply_to"]
    images = list(images or [])
    msg.set_content(body + ("\n\n" + "\n".join(images) if images else ""))
    img_html = "".join(
        f'<p><img src="{escape(url)}" alt="" style="max-width:100%;height:auto;border:0"></p>' for url in images
    )
    html = (
        '<!doctype html><html><body style="font-family:Arial,sans-serif;font-size:15px;'
        'line-height:1.5;color:#14213a;max-width:600px">' + text_to_html(body) + img_html + "</body></html>"
    )
    msg.add_alternative(html, subtype="html")
    return msg


def send(to, subject, body, cfg=None, server=None, images=None):
    """Eine Mail senden. Wirft MailError mit verständlicher Meldung."""
    cfg = cfg or load()
    msg = build_message(cfg, to, subject, body, images)
    try:
        if server is not None:
            server.send_message(msg)
            return
        with _connect(cfg) as srv:
            srv.send_message(msg)
    except MailError:
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError("Anmeldung am Mailserver fehlgeschlagen – Benutzer oder Passwort prüfen.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Versand fehlgeschlagen: {exc}") from exc


def send_async(to, subject, body, images=None):
    """Für Formular-Antworten: nicht auf den Mailserver warten."""
    app = current_app._get_current_object()
    cfg = load()

    def run():
        try:
            send(to, subject, body, cfg, images=images)
        except MailError as exc:
            app.logger.error("Mail an %s fehlgeschlagen: %s", to, exc)

    if app.config.get("MAIL_ASYNC", True):
        threading.Thread(target=run, daemon=True).start()
    else:
        run()


def describe_error(exc):
    """Verständliche Meldung für das Testprotokoll."""
    if isinstance(exc, MailError):
        return str(exc)
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        detail = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) else exc.smtp_error
        return f"Anmeldung abgelehnt ({exc.smtp_code} {detail}) – Benutzername oder Passwort prüfen."
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return f"{exc} – Verschlüsselung STARTTLS oder SSL wählen."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Empfänger abgelehnt: " + ", ".join(exc.recipients)
    if isinstance(exc, smtplib.SMTPSenderRefused):
        detail = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) else exc.smtp_error
        return f"Absenderadresse {exc.sender} abgelehnt ({exc.smtp_code} {detail}) – sie muss zum SMTP-Konto passen."
    if isinstance(exc, ssl.SSLError):
        return f"TLS-Fehler: {exc} – passt die Verschlüsselung zum Port?"
    if isinstance(exc, (TimeoutError, smtplib.SMTPServerDisconnected)):
        return f"{exc.__class__.__name__}: {exc or 'keine Antwort'} – passt die Verschlüsselung zum Port?"
    return f"{exc.__class__.__name__}: {exc}"


def smtp_test(cfg, to=None):
    """Probiert die eingestellte Variante, danach 587/STARTTLS und 465/SSL.
    Bei abgelehnter Anmeldung wird abgebrochen: Ein anderer Port ändert daran nichts,
    und jeder weitere Fehlversuch zählt bei fail2ban auf dem Mailserver mit.
    Gibt (erfolgreiche Variante oder None, Protokollzeilen) zurück."""
    variants = [(int(cfg.get("smtp_port") or 587), cfg.get("smtp_security", "starttls"))]
    variants += [v for v in VARIANTS if v not in variants]
    log = []
    for port, security in variants:
        label = f"Port {port} mit {security.upper()}"
        try:
            with _connect(cfg, port, security) as srv:
                if to:
                    msg = build_message(
                        cfg, to, "Testmail der Sponsorenlauf-App",
                        f"Diese Testmail wurde am {datetime.now():%d.%m.%Y um %H:%M} Uhr über {cfg.get('smtp_host')}, "
                        f"Port {port} ({security.upper()}) verschickt.\n\nDer Mailversand funktioniert.",
                    )
                    srv.send_message(msg)
            log.append(f"{label}: erfolgreich" + (f", Testmail an {to} gesendet" if to else ""))
            return (port, security), log
        except Exception as exc:  # noqa: BLE001 – jede Ursache soll im Protokoll landen
            log.append(f"{label}: {describe_error(exc)}")
            if isinstance(exc, (MailError, smtplib.SMTPAuthenticationError,
                                smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused)):
                break
    return None, log


# ---------------------------------------------------------------- Rundmail

def start_rundmail(rundmail_id):
    app = current_app._get_current_object()
    if app.config.get("MAIL_ASYNC", True):
        threading.Thread(target=_run_rundmail, args=(app, rundmail_id), daemon=True).start()
    else:
        _run_rundmail(app, rundmail_id)


def _run_rundmail(app, rundmail_id):
    from .logic import sponsor_ctx, stats
    from .util import render_placeholders

    with app.app_context():
        con = dbmod.connect(app.config["DATABASE"])
        try:
            cfg = load(con)
            st = stats(con, cfg)
            mail = con.execute("SELECT * FROM rundmail WHERE id = ?", (rundmail_id,)).fetchone()
            con.execute("UPDATE rundmail SET status = 'läuft' WHERE id = ?", (rundmail_id,))
            con.commit()
            pending = con.execute(
                "SELECT * FROM rundmail_empfaenger WHERE rundmail_id = ? AND status != 'gesendet'", (rundmail_id,)
            ).fetchall()
            rate = max(0.0, float(cfg.get("mail_rate_seconds") or 1))
            images = bild_urls(mail["bilder"])
            server = None
            for i, rec in enumerate(pending):
                sp = con.execute("SELECT * FROM sponsor WHERE id = ?", (rec["sponsor_id"],)).fetchone()
                if sp is None:
                    con.execute(
                        "UPDATE rundmail_empfaenger SET status='fehler', fehler=?, zeit=? WHERE id=?",
                        ("Sponsor gelöscht", now_iso(), rec["id"]),
                    )
                    con.commit()
                    continue
                lang = "en" if sp["sprache"] == "en" and (mail["text_en"] or "").strip() else "de"
                betreff, text = (mail["betreff_en"], mail["text_en"]) if lang == "en" else (mail["betreff"], mail["text"])
                ctx = sponsor_ctx(sp, cfg, st, lang=lang)
                try:
                    if server is None:
                        server = _connect(cfg)
                    send(rec["email"], render_placeholders(betreff, ctx),
                         render_placeholders(text, ctx), cfg, server=server, images=images)
                    con.execute(
                        "UPDATE rundmail_empfaenger SET status='gesendet', fehler=NULL, zeit=? WHERE id=?",
                        (now_iso(), rec["id"]),
                    )
                except Exception as exc:  # noqa: BLE001
                    con.execute(
                        "UPDATE rundmail_empfaenger SET status='fehler', fehler=?, zeit=? WHERE id=?",
                        (str(exc)[:500], now_iso(), rec["id"]),
                    )
                    if server is not None:
                        try:
                            server.quit()
                        except Exception:  # noqa: BLE001
                            pass
                        server = None
                con.commit()
                if i < len(pending) - 1 and rate:
                    time.sleep(rate)
            if server is not None:
                try:
                    server.quit()
                except Exception:  # noqa: BLE001
                    pass
            errors = con.execute(
                "SELECT COUNT(*) FROM rundmail_empfaenger WHERE rundmail_id=? AND status='fehler'", (rundmail_id,)
            ).fetchone()[0]
            con.execute(
                "UPDATE rundmail SET status=?, gesendet_am=? WHERE id=?",
                ("mit Fehlern" if errors else "gesendet", now_iso(), rundmail_id),
            )
            con.commit()
        except Exception:  # noqa: BLE001
            app.logger.exception("Rundmail %s abgebrochen", rundmail_id)
            con.execute("UPDATE rundmail SET status='abgebrochen' WHERE id=?", (rundmail_id,))
            con.commit()
        finally:
            con.close()
