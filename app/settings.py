"""Alle im Admin-Bereich pflegbaren Einstellungen samt Standardwerten."""
import os

from flask import g

from .db import get_db

IMPRESSUM = """Angaben gemäß § 5 DDG

[Vorname Nachname]
[Straße und Hausnummer]
[PLZ Ort]

E-Mail: [E-Mail-Adresse]

Inhaltlich verantwortlich: [Vorname Nachname], Anschrift wie oben.

Private, nicht kommerzielle Seite zum Sponsorenlauf der [Schule]. Der Erlös geht an den Förderverein der Schule."""

DATENSCHUTZ = """Verantwortlich
Verantwortlich für die Datenverarbeitung auf dieser Seite ist [Vorname Nachname] (Kontakt siehe Impressum).

Welche Daten wir verarbeiten
Wenn du dich als Sponsor einträgst, speichern wir deinen Namen, deine E-Mail-Adresse, deinen Betrag pro Runde, einen eventuellen Höchstbetrag, ein freiwilliges Bild und – nur wenn du eine Spendenquittung möchtest – Name und Anschrift für die Quittung. Außerdem speichern wir den Zeitpunkt deiner Anmeldung und deiner Bestätigung.

Wozu
Wir nutzen die Daten, um deine Zusage zu bestätigen, dich am Lauftag zu informieren, dir nach dem Lauf deinen Betrag mitzuteilen und die Zahlung nachzuhalten. Name und Bild erscheinen in der öffentlichen Sponsorenliste, außer du wählst „anonym“. Deine E-Mail-Adresse wird nie veröffentlicht. Es gibt keinen Newsletter und keine Weitergabe zu Werbezwecken.

Rechtsgrundlage
Deine Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), die du über den Bestätigungslink erteilst, sowie die Abwicklung deiner Zusage (Art. 6 Abs. 1 lit. b DSGVO).

Weitergabe
Die Sponsorenkarte mit Namen, Beträgen und – falls gewünscht – Quittungsanschrift geben wir an die [Schule] und ihren Förderverein weiter, damit das Geld zugeordnet und eine Spendenbescheinigung ausgestellt werden kann. Wenn du per PayPal zahlst, gelten zusätzlich die Datenschutzbestimmungen von PayPal.

Speicherdauer
Wir löschen alle Sponsordaten und Bilder spätestens drei Monate nach dem Lauf. Auf Wunsch löschen wir deine Daten jederzeit früher.

Cookies und Server
Die Seite setzt nur ein technisch notwendiges Sitzungs-Cookie für das Formular. Es gibt kein Tracking und keine externen Schriften oder Skripte. Der Webserver protokolliert technisch bedingt IP-Adressen; diese Protokolle werden nach kurzer Zeit gelöscht.

Deine Rechte
Du hast das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung, Datenübertragbarkeit und Widerruf deiner Einwilligung. Eine kurze Mail genügt. Außerdem kannst du dich bei einer Datenschutz-Aufsichtsbehörde beschweren, in NRW bei der LDI NRW."""

TPL_CONFIRM_BODY = """Hallo {name},

danke, dass du {laeufer} beim Sponsorenlauf der {schule} am {lauf_datum} unterstützt!

Deine Zusage: {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis}.

Bitte bestätige sie mit einem Klick auf diesen Link:
{bestaetigungslink}

Der Link ist 7 Tage gültig. Erst nach der Bestätigung erscheinst du in der Sponsorenliste.

Falls du dich nicht selbst angemeldet hast, ignoriere diese Mail einfach.

Viele Grüße
{laeufer} und Familie
{seite}"""

TPL_ALREADY_BODY = """Hallo {name},

du bist schon dabei: Du unterstützt {laeufer} mit {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis}.

Möchtest du etwas ändern, antworte einfach auf diese Mail.

Viele Grüße
{laeufer} und Familie
{seite}"""

TPL_WELCOME_BODY = """Hallo {name},

wir haben deine Zusage für den Sponsorenlauf eingetragen: {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis}. Vielen Dank!

Hier siehst du alle Sponsoren: {seite}

Viele Grüße
{laeufer} und Familie"""

TPL_TRAINING_BODY = """Hallo {name},

{laeufer} trainiert fleißig für den Sponsorenlauf am {lauf_datum}! Schon jetzt ein großes Dankeschön, dass du {laeufer} mit {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis} unterstützt.

Wir halten dich auf dem Laufenden – bald geht's los!

Viele Grüße
{laeufer} und Familie
{seite}"""

TPL_REMINDER_BODY = """Hallo {name},

heute ist es so weit: {laeufer} läuft beim Sponsorenlauf der {schule}!

Du bist mit {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis} dabei. Nach dem Lauf bekommst du eine Mail mit dem Ergebnis und deinem Betrag.

Drück die Daumen!
{laeufer} und Familie
{seite}"""

TPL_PLAETZE_BODY = """Hallo {name},

auf die Plätze, fertig …: {laeufer} steht gerade an der Startlinie beim Sponsorenlauf der {schule}! Gleich fällt der Startschuss.

Du bist mit {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis} dabei. Den Stand siehst du gleich live auf {seite}

Drück die Daumen!
{laeufer} und Familie"""

TPL_START_BODY = """Hallo {name},

jetzt geht's los: {laeufer} ist gerade beim Sponsorenlauf der {schule} gestartet!

Du bist mit {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis} dabei. Den Stand siehst du live auf {seite}

Nach dem Lauf bekommst du eine Mail mit dem Ergebnis und deinem Betrag.

Drück die Daumen!
{laeufer} und Familie"""

TPL_VORLAEUFIG_BODY = """Hallo {name},

geschafft: Der Sponsorenlauf ist zu Ende! {laeufer} hat nach vorläufiger Zählung {runden} Runden geschafft, das sind {strecke_km}.

Mit deiner Zusage von {betrag_pro_runde} pro Runde{hoechstbetrag_hinweis} wären das {spende}. Zusammen mit allen Sponsoren sind bisher {summe_gesamt} zusammengekommen.

Das Ergebnis ist noch vorläufig. Sobald die Rundenzahl offiziell bestätigt ist, bekommst du eine Mail mit dem endgültigen Betrag und den Zahlungsmöglichkeiten.

Danke fürs Mitfiebern!
{laeufer} und Familie
{seite}"""

TPL_RESULT_BODY = """Hallo {name},

{laeufer} hat beim Sponsorenlauf {runden} Runden geschafft, das sind {strecke_km}. Zusammen mit allen Sponsoren sind {summe_gesamt} für den neuen Schulhof zusammengekommen.

Dein Beitrag: {spende} ({runden} Runden × {betrag_pro_runde}{hoechstbetrag_hinweis}).

So kannst du zahlen:
- per PayPal: {paypal_link}
- per PayPal „Freunde und Familie“ an {paypal_adresse}, bitte mit deinem Namen
- oder bar bei uns

Wir geben das Geld gesammelt im Umschlag an die Klassenlehrerin der Klasse {klasse}. Es geht an den Förderverein der {schule}.

Spendenbescheinigung: Der Förderverein stellt auf Wunsch eine Spendenbescheinigung aus. Falls du bei der Anmeldung keine Anschrift angegeben hast, antworte einfach mit Name und Anschrift auf diese Mail.

Danke für deine Unterstützung!
{laeufer} und Familie"""

TPL_CONFIRM_BODY_EN = """Hi {name},

thank you for supporting {laeufer} in the sponsored run of {schule} on {lauf_datum}!

Your pledge: {betrag_pro_runde} per lap{hoechstbetrag_hinweis}.

Please confirm it with one click on this link:
{bestaetigungslink}

The link is valid for 7 days. You'll only appear in the sponsor list after confirming.

If you didn't sign up yourself, just ignore this email.

Best wishes,
{laeufer} and family
{seite}"""

TPL_ALREADY_BODY_EN = """Hi {name},

you're already in: you're supporting {laeufer} with {betrag_pro_runde} per lap{hoechstbetrag_hinweis}.

If you'd like to change anything, just reply to this email.

Best wishes,
{laeufer} and family
{seite}"""

TPL_WELCOME_BODY_EN = """Hi {name},

we've recorded your pledge for the sponsored run: {betrag_pro_runde} per lap{hoechstbetrag_hinweis}. Thank you very much!

You can see all sponsors here: {seite}

Best wishes,
{laeufer} and family"""

TPL_TRAINING_BODY_EN = """Hi {name},

{laeufer} is training hard for the sponsored run on {lauf_datum}! A big thank you already for supporting {laeufer} with {betrag_pro_runde} per lap{hoechstbetrag_hinweis}.

We'll keep you posted – it won't be long now!

Best wishes,
{laeufer} and family
{seite}"""

TPL_REMINDER_BODY_EN = """Hi {name},

today's the day: {laeufer} is running in the sponsored run of {schule}!

You're in with {betrag_pro_runde} per lap{hoechstbetrag_hinweis}. After the run you'll get an email with the result and your amount.

Fingers crossed!
{laeufer} and family
{seite}"""

TPL_PLAETZE_BODY_EN = """Hi {name},

on your marks, get set …: {laeufer} is standing at the starting line of the sponsored run of {schule}! The starting signal is about to go off.

You're in with {betrag_pro_runde} per lap{hoechstbetrag_hinweis}. Follow it live soon at {seite}

Fingers crossed!
{laeufer} and family"""

TPL_START_BODY_EN = """Hi {name},

here we go: {laeufer} has just started in the sponsored run of {schule}!

You're in with {betrag_pro_runde} per lap{hoechstbetrag_hinweis}. Follow it live at {seite}

After the run you'll get an email with the result and your amount.

Fingers crossed!
{laeufer} and family"""

TPL_VORLAEUFIG_BODY_EN = """Hi {name},

done: the sponsored run is over! According to the provisional count, {laeufer} managed {runden} laps, that's {strecke_km}.

With your pledge of {betrag_pro_runde} per lap{hoechstbetrag_hinweis}, that would be {spende}. Together with all sponsors, {summe_gesamt} has been raised so far.

This result is still provisional. As soon as the lap count is officially confirmed, you'll get an email with the final amount and how to pay.

Thanks for cheering along!
{laeufer} and family
{seite}"""

TPL_RESULT_BODY_EN = """Hi {name},

{laeufer} managed {runden} laps in the sponsored run, that's {strecke_km}. Together with all sponsors, {summe_gesamt} was raised for the new schoolyard.

Your contribution: {spende} ({runden} laps × {betrag_pro_runde}{hoechstbetrag_hinweis}).

How you can pay:
- via PayPal: {paypal_link}
- via PayPal "Friends and Family" to {paypal_adresse}, please include your name
- or cash with us

We'll hand the money collected in an envelope to the class teacher of class {klasse}. It goes to the parents' association of {schule}.

Donation receipt: The parents' association will issue a donation receipt on request. If you didn't give an address at sign-up, just reply with your name and address to this email.

Thank you for your support!
{laeufer} and family"""

DEFAULTS = {
    # Läufer und Veranstaltung
    "laeufer_name": "Max",
    "karten_name": "Max Mustermann",
    "klasse": "2a",
    "schule": "Musterschule",
    "lauf_datum": "2026-09-25",
    "rundenlaenge_m": "100",
    "laeufer_bild": "",
    "marke": "{laeufer} rennt",
    "headline": "{laeufer} läuft für den neuen Schulhof",
    "intro": "Sag einen Betrag pro gelaufener Runde zu. Nach dem Lauf zahlst du Runden mal Betrag – auf Wunsch mit Höchstbetrag.",
    "zweck": "Der Erlös geht an den Förderverein der Schule und hilft, den Schulhof nach den Bauarbeiten neu zu gestalten.",
    "max_betrag_cent": "10000",
    "mindestbeitrag_cent": "20",       # 0 = Mindestspende-Feature ausgeschaltet
    "hoechst_faktor": "10",
    "sponsor_sort_feld": "datum",      # name | datum | betrag
    "sponsor_sort_richtung": "ab",     # auf | ab
    "sponsor_pro_seite": "25",         # 0 = aus, sonst 5/10/25/50/100
    "sponsor_zeige_zeitpunkt": "0",    # Zeitpunkt der Bestätigung anzeigen (relativ, in "Ergebnis" absolut)
    "ablauf_text": "Du sagst einen Betrag pro Runde zu und bestätigst das per Mail. Am Lauftag dreht der Läufer "
                   "so viele Runden wie möglich. Danach steht hier das Ergebnis, und jeder Sponsor bekommt eine "
                   "Mail mit seinem Betrag und einem Zahlungslink.",
    "footer_text": "Sponsorenlauf der {schule} am {lauf_datum}. Der Erlös geht an den Förderverein der Schule.",
    # Englische Fassungen der Freitexte (optional, leer = Fallback Deutsch)
    "marke_en": "",
    "headline_en": "",
    "intro_en": "",
    "zweck_en": "",
    "ablauf_text_en": "",
    "footer_text_en": "",
    "absage_text_en": "",
    "impressum_en": "",
    "datenschutz_en": "",
    # Anmeldung
    "bestaetigungsseite": "0",   # 1 = eigene Seite mit Klick nötig, 0 (Standard) = Linkklick bestätigt direkt
    # Ablauf
    "phase": "sammeln",          # sammeln | ergebnis
    "live_aktiv": "0",
    "abgesagt": "0",
    "absage_text": "",
    "runden": "0",
    # Countdown und Laufuhr
    "countdown_aktiv": "1",            # Countdown vor dem Lauf auf der Startseite
    "start_zeit": "2026-09-25T10:45",  # Ortszeit Berlin, Format von <input type="datetime-local">
    "laufdauer_s": "600",              # Laufdauer in Sekunden, die Laufuhr zählt davon rückwärts
    "lauf_gestartet_am": "",           # UTC-ISO-Zeitpunkt des Starts, leer = nicht gestartet
    "ende_zeit": "",                   # vom Admin eingetragenes Laufende (Ortszeit Berlin, wie start_zeit), leer = offen
    # Zahlung
    "paypal_empfaenger": "",
    "paypal_me": "",
    # Rechtliches
    "impressum": IMPRESSUM,
    "datenschutz": DATENSCHUTZ,
    # Mailserver
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_security": "starttls",  # starttls | ssl | none
    "smtp_user": "",
    "smtp_password": "",
    "mail_from": "",
    "mail_from_name": "Sponsorenlauf",
    "mail_reply_to": "",
    "mail_rate_seconds": "1",
    # Vorlagen
    "tpl_confirm_subject": "Bitte bestätige deine Zusage für {laeufer}",
    "tpl_confirm_body": TPL_CONFIRM_BODY,
    "tpl_already_subject": "Du bist schon dabei",
    "tpl_already_body": TPL_ALREADY_BODY,
    "tpl_welcome_subject": "Danke für deine Unterstützung, {name}",
    "tpl_welcome_body": TPL_WELCOME_BODY,
    "tpl_training_subject": "{laeufer} trainiert für den Sponsorenlauf!",
    "tpl_training_body": TPL_TRAINING_BODY,
    "tpl_reminder_subject": "Heute läuft {laeufer}!",
    "tpl_reminder_body": TPL_REMINDER_BODY,
    "tpl_plaetze_subject": "Auf die Plätze: {laeufer} steht am Start!",
    "tpl_plaetze_body": TPL_PLAETZE_BODY,
    "tpl_start_subject": "{laeufer} ist gestartet!",
    "tpl_start_body": TPL_START_BODY,
    "tpl_vorlaeufig_subject": "Geschafft! {laeufer} ist {runden} Runden gelaufen (vorläufig)",
    "tpl_vorlaeufig_body": TPL_VORLAEUFIG_BODY,
    "tpl_result_subject": "{laeufer} ist {runden} Runden gelaufen – danke!",
    "tpl_result_body": TPL_RESULT_BODY,
    # Bilder je Vorlage (Dateinamen in uploads/, eine pro Zeile), gelten für beide Sprachen
    "tpl_confirm_bilder": "",
    "tpl_already_bilder": "",
    "tpl_welcome_bilder": "",
    "tpl_training_bilder": "",
    "tpl_reminder_bilder": "",
    "tpl_plaetze_bilder": "",
    "tpl_start_bilder": "",
    "tpl_vorlaeufig_bilder": "",
    "tpl_result_bilder": "",
    "start_mail_aktiv": "0",           # 1 = beim Start des Laufs Vorlage „Start“ an alle bestätigten Sponsoren
    "ende_mail_aktiv": "0",            # 1 = nach Ablauf der Laufuhr Vorlage „Vorläufiges Ergebnis“ an alle bestätigten
    "ende_mail_gesendet_am": "",       # UTC-ISO-Zeitpunkt des Versands, leer = für diesen Start noch nicht gesendet
    # Englische Fassungen der Mailvorlagen (echter Standardtext, kein leeres Feld)
    "tpl_confirm_subject_en": "Please confirm your pledge for {laeufer}",
    "tpl_confirm_body_en": TPL_CONFIRM_BODY_EN,
    "tpl_already_subject_en": "You're already in",
    "tpl_already_body_en": TPL_ALREADY_BODY_EN,
    "tpl_welcome_subject_en": "Thank you for your support, {name}",
    "tpl_welcome_body_en": TPL_WELCOME_BODY_EN,
    "tpl_training_subject_en": "{laeufer} is training for the sponsored run!",
    "tpl_training_body_en": TPL_TRAINING_BODY_EN,
    "tpl_reminder_subject_en": "{laeufer} is running today!",
    "tpl_reminder_body_en": TPL_REMINDER_BODY_EN,
    "tpl_plaetze_subject_en": "On your marks: {laeufer} is at the start!",
    "tpl_plaetze_body_en": TPL_PLAETZE_BODY_EN,
    "tpl_start_subject_en": "{laeufer} has started!",
    "tpl_start_body_en": TPL_START_BODY_EN,
    "tpl_vorlaeufig_subject_en": "Done! {laeufer} ran {runden} laps (provisional)",
    "tpl_vorlaeufig_body_en": TPL_VORLAEUFIG_BODY_EN,
    "tpl_result_subject_en": "{laeufer} ran {runden} laps – thank you!",
    "tpl_result_body_en": TPL_RESULT_BODY_EN,
}

TRANSLATABLE = [
    "marke", "headline", "intro", "zweck", "ablauf_text", "footer_text", "absage_text", "impressum", "datenschutz",
    "tpl_confirm_subject", "tpl_confirm_body",
    "tpl_already_subject", "tpl_already_body",
    "tpl_welcome_subject", "tpl_welcome_body",
    "tpl_training_subject", "tpl_training_body",
    "tpl_reminder_subject", "tpl_reminder_body",
    "tpl_plaetze_subject", "tpl_plaetze_body",
    "tpl_start_subject", "tpl_start_body",
    "tpl_vorlaeufig_subject", "tpl_vorlaeufig_body",
    "tpl_result_subject", "tpl_result_body",
]

# Werte, die beim allerersten Start aus der .env übernommen werden können
ENV_SEED = {
    "smtp_host": "SMTP_HOST",
    "smtp_port": "SMTP_PORT",
    "smtp_security": "SMTP_SECURITY",
    "smtp_user": "SMTP_USER",
    "smtp_password": "SMTP_PASSWORD",
    "mail_from": "MAIL_FROM",
}


def seed(con):
    existing = {r[0] for r in con.execute("SELECT key FROM einstellung")}
    for key, value in DEFAULTS.items():
        if key in existing:
            continue
        env_name = ENV_SEED.get(key)
        if env_name and os.environ.get(env_name):
            value = os.environ[env_name]
        con.execute("INSERT INTO einstellung(key, value) VALUES (?, ?)", (key, value))


def load(con=None):
    con = con or get_db()
    values = dict(DEFAULTS)
    values.update({r["key"]: r["value"] for r in con.execute("SELECT key, value FROM einstellung")})
    return values


def get_all():
    if "settings" not in g:
        g.settings = load()
    return g.settings


def save(updates, con=None):
    con = con or get_db()
    for key, value in updates.items():
        if key not in DEFAULTS:
            raise KeyError(key)
        con.execute(
            "INSERT INTO einstellung(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, "" if value is None else str(value)),
        )
    con.commit()
    g.pop("settings", None)


def as_int(s, key, default=0):
    try:
        return int(s.get(key, default))
    except (TypeError, ValueError):
        return default


def localize(s, lang):
    """Liefert s unverändert für Deutsch, sonst eine Kopie mit den englischen
    Fassungen aus TRANSLATABLE, soweit diese nicht leer sind (sonst Deutsch)."""
    if lang != "en":
        return s
    out = dict(s)
    for key in TRANSLATABLE:
        en = s.get(f"{key}_en")
        if en:
            out[key] = en
    return out


def flag(s, key):
    return s.get(key) == "1"
