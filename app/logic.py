"""Fachlogik: Phase der Seite, Erlösberechnung, Statistik, Platzhalter."""
from datetime import datetime, timedelta, timezone

from flask import current_app

from .settings import as_int, flag
from .util import (BERLIN, bild_urls, fmt_date_de, fmt_dt, fmt_euro, fmt_km, fmt_relative, parse_iso,
                   paypal_link, render_placeholders)

ORDER = "betrag_cent DESC, COALESCE(bestaetigt_am, erstellt_am) ASC, id ASC"

SORT_SPALTEN = {
    "name": "name COLLATE NOCASE",
    "datum": "COALESCE(bestaetigt_am, erstellt_am)",
    "betrag": "betrag_cent",
}


def sponsor_order_sql(s):
    """ORDER BY für die öffentliche Sponsorenliste, nach Admin-Einstellung."""
    spalte = SORT_SPALTEN.get(s.get("sponsor_sort_feld"), SORT_SPALTEN["datum"])
    richtung = "ASC" if s.get("sponsor_sort_richtung") == "auf" else "DESC"
    return f"{spalte} {richtung}, id ASC"


def mode(s):
    """abgesagt > ergebnis > live > sammeln"""
    if flag(s, "abgesagt"):
        return "abgesagt"
    if s.get("phase") == "ergebnis":
        return "ergebnis"
    if flag(s, "live_aktiv"):
        return "live"
    return "sammeln"


def ortszeit(value):
    """Wert aus <input type="datetime-local"> (Ortszeit Berlin) als aware datetime oder None."""
    try:
        return datetime.strptime(value or "", "%Y-%m-%dT%H:%M").replace(tzinfo=BERLIN)
    except (TypeError, ValueError):
        return None


def start_zeit(s):
    """Startzeit aus den Einstellungen (Ortszeit Berlin) als aware datetime oder None."""
    return ortszeit(s.get("start_zeit", ""))


def lauf_start(s):
    try:
        return parse_iso(s.get("lauf_gestartet_am"))
    except ValueError:
        return None


def _ms(dt):
    return int(dt.timestamp() * 1000)


def clock(s, now=None):
    """Uhr auf der Startseite: Countdown bis zum Start, Restzeit im Lauf oder Ergebnis.
    None = keine Uhr anzeigen."""
    now = now or datetime.now(timezone.utc)
    mode_ = mode(s)
    ziel, art = None, None
    if mode_ == "sammeln" and flag(s, "countdown_aktiv"):
        art, ziel = "countdown", start_zeit(s)
    elif mode_ == "live":
        start = lauf_start(s)
        if start:
            art, ziel = "lauf", start + timedelta(seconds=max(1, as_int(s, "laufdauer_s", 600)))
    elif mode_ == "ergebnis":
        return {"art": "ergebnis"}
    if ziel is None:
        return None
    rest = max(0, int((ziel - now).total_seconds() + 0.999))
    return {"art": art, "ziel_ms": _ms(ziel), "jetzt_ms": _ms(now), "rest_s": rest}


ENDE_MAIL_KARENZ_S = 60       # Zeit nach Ablauf der Laufuhr, um die letzte Runde noch einzutragen
ENDE_MAIL_SPAETESTENS_S = 3600  # später nicht mehr automatisch senden (z. B. vergessener Probestart)


def lauf_ende(s):
    start = lauf_start(s)
    if start is None:
        return None
    return start + timedelta(seconds=max(1, as_int(s, "laufdauer_s", 600)))


def ende_mail_zeitpunkt(s):
    """Zeitpunkt, ab dem die Mail „Vorläufiges Ergebnis“ fällig wird, oder None, wenn sie nicht ansteht."""
    if not flag(s, "ende_mail_aktiv") or s.get("ende_mail_gesendet_am") or mode(s) != "live":
        return None
    ende = lauf_ende(s)
    return ende + timedelta(seconds=ENDE_MAIL_KARENZ_S) if ende else None


def ende_mail_zeitpunkt_ms(s):
    zeitpunkt = ende_mail_zeitpunkt(s)
    return _ms(zeitpunkt) if zeitpunkt else None


def ende_mail_faellig(s, now=None):
    zeitpunkt = ende_mail_zeitpunkt(s)
    if zeitpunkt is None:
        return False
    now = now or datetime.now(timezone.utc)
    return zeitpunkt <= now <= zeitpunkt + timedelta(seconds=ENDE_MAIL_SPAETESTENS_S)


def ende_mail_manuell_moeglich(s):
    """Beim Speichern von Endzeit und vorläufiger Rundenzahl: Mail sofort senden, wenn eingeschaltet
    und für diesen Lauf noch nicht gesendet – unabhängig von der Laufuhr."""
    return flag(s, "ende_mail_aktiv") and not s.get("ende_mail_gesendet_am") and mode(s) != "abgesagt"


def fmt_rest(rest_s, tage_wort="Tage"):
    """Restzeit als 'MM:SS', 'HH:MM:SS' oder 'X Tage HH:MM:SS' (gleiche Logik wie in app.js)."""
    tage, rest = divmod(rest_s, 86400)
    h, rest = divmod(rest, 3600)
    m, sec = divmod(rest, 60)
    text = f"{h:02d}:{m:02d}:{sec:02d}" if h or tage else f"{m:02d}:{sec:02d}"
    return f"{tage} {tage_wort} {text}" if tage else text


def registration_open(s):
    return mode(s) == "sammeln"


def laeufer(s):
    return (s.get("laeufer_name") or "Max").strip()


def erloes_cent(sponsor, runden):
    total = int(runden) * int(sponsor["betrag_cent"])
    cap = sponsor["hoechst_cent"]
    if cap:
        total = min(total, int(cap))
    return total


def zeitpunkt_text(sponsor, mode_):
    """Zeitpunkt der Sponsorenerklärung: relativ ('vor X Minuten'), in Phase
    'Ergebnis' absolut als DD.MM.YYYY."""
    ts = sponsor["bestaetigt_am"] or sponsor["erstellt_am"]
    if mode_ == "ergebnis":
        return fmt_dt(ts, with_time=False)
    return fmt_relative(ts)


def confirmed(db, s=None):
    """Bestätigte Sponsoren. Ohne s (z. B. Sponsorenkarte) feste Reihenfolge nach Betrag;
    mit s (öffentliche Liste) nach der Admin-Einstellung sortiert."""
    order = sponsor_order_sql(s) if s is not None else ORDER
    return db.execute(f"SELECT * FROM sponsor WHERE status = 'bestaetigt' ORDER BY {order}").fetchall()


def hoechst_mode(sponsor, s):
    """'show' = 'höchstens X €' anzeigen, 'footnote' = nur Fußnotenzeichen, 'none' = kein Höchstbetrag.

    Ein sehr hoher Höchstbetrag (z. B. das 50-fache des Rundenbetrags) wird in der Praxis
    nie erreicht und ist für Betrachter wenig aussagekräftig – dafür steht die Schwelle
    'hoechst_faktor' (Standard 10): erst darunter wird der Höchstbetrag explizit genannt."""
    cap = sponsor["hoechst_cent"]
    if not cap:
        return "none"
    try:
        faktor = float(str(s.get("hoechst_faktor", "10")).replace(",", ".") or "10")
    except ValueError:
        faktor = 10.0
    return "show" if cap < faktor * sponsor["betrag_cent"] else "footnote"


def stats(db, s):
    rows = confirmed(db)
    runden = as_int(s, "runden")
    total = sum(erloes_cent(r, runden) for r in rows)
    bezahlt = sum(erloes_cent(r, runden) for r in rows if r["bezahlt_am"])
    unconfirmed = db.execute("SELECT COUNT(*) FROM sponsor WHERE status != 'bestaetigt'").fetchone()[0]
    return {
        "anzahl": len(rows),
        "unbestaetigt": unconfirmed,
        "pro_runde": sum(r["betrag_cent"] for r in rows),
        "runden": runden,
        "meter": runden * as_int(s, "rundenlaenge_m", 100),
        "summe": total,
        "bezahlt": bezahlt,
        "offen": total - bezahlt,
        "anzahl_bezahlt": sum(1 for r in rows if r["bezahlt_am"]),
    }


HOECHST_NONE = {"de": "ohne", "en": "none"}
HOECHST_HINWEIS = {"de": ", höchstens {betrag}", "en": ", max. {betrag}"}


def base_ctx(s, st=None, lang="de"):
    st = st or {}
    return {
        "laeufer": laeufer(s),
        "schule": s.get("schule", ""),
        "klasse": s.get("klasse", ""),
        "lauf_datum": fmt_date_de(s.get("lauf_datum", "")),
        "runden": st.get("runden", as_int(s, "runden")),
        "strecke_km": fmt_km(st.get("meter", 0)),
        "summe_gesamt": fmt_euro(st.get("summe", 0)),
        "paypal_adresse": s.get("paypal_empfaenger", ""),
        "ablauf": s.get("ablauf_text", ""),
        "seite": current_app.config["BASE_URL"] + "/",
    }


def sponsor_ctx(sponsor, s, st, extra=None, lang="de"):
    ctx = base_ctx(s, st, lang)
    spende = erloes_cent(sponsor, ctx["runden"])
    cap = sponsor["hoechst_cent"]
    ctx.update(
        {
            "name": sponsor["name"],
            "email": sponsor["email"] or "",
            "betrag_pro_runde": fmt_euro(sponsor["betrag_cent"]),
            "hoechstbetrag": fmt_euro(cap) if cap else HOECHST_NONE.get(lang, HOECHST_NONE["de"]),
            "hoechstbetrag_hinweis": HOECHST_HINWEIS.get(lang, HOECHST_HINWEIS["de"]).format(betrag=fmt_euro(cap))
            if cap else "",
            "spende": fmt_euro(spende),
            "paypal_link": paypal_link(s, spende, sponsor["name"]) if spende else "",
        }
    )
    if extra:
        ctx.update(extra)
    return ctx


def render_template_pair(s, key, ctx):
    subject = render_placeholders(s.get(f"tpl_{key}_subject", ""), ctx)
    body = render_placeholders(s.get(f"tpl_{key}_body", ""), ctx)
    return subject, body, bild_urls(s.get(f"tpl_{key}_bilder", ""))


def headline(s):
    return render_placeholders(s.get("headline", ""), {"laeufer": laeufer(s)})


def marke(s):
    return render_placeholders(s.get("marke", ""), {"laeufer": laeufer(s)})


def footer_text(s):
    return render_placeholders(
        s.get("footer_text", ""),
        {"laeufer": laeufer(s), "schule": s.get("schule", ""), "lauf_datum": fmt_date_de(s.get("lauf_datum", ""))},
    )


PLACEHOLDER_HELP = [
    ("{name}", "Name des Sponsors"),
    ("{email}", "E-Mail-Adresse des Sponsors"),
    ("{laeufer}", "Läufername"),
    ("{schule}", "Schule"),
    ("{klasse}", "Klasse"),
    ("{lauf_datum}", "Datum des Laufs"),
    ("{runden}", "gelaufene Runden"),
    ("{strecke_km}", "Strecke in km"),
    ("{betrag_pro_runde}", "Zusage pro Runde"),
    ("{hoechstbetrag}", "Höchstbetrag oder „ohne“"),
    ("{hoechstbetrag_hinweis}", "„, höchstens 30,00 €“ oder leer"),
    ("{spende}", "persönlicher Betrag (Runden × Zusage, gedeckelt)"),
    ("{summe_gesamt}", "Summe aller Spenden"),
    ("{paypal_link}", "PayPal-Link mit persönlichem Betrag"),
    ("{paypal_adresse}", "PayPal-Empfänger"),
    ("{ablauf}", "Ablauf des Sponsorenlaufs (aus den Einstellungen)"),
    ("{seite}", "Adresse der Website"),
    ("{bestaetigungslink}", "nur Bestätigungsmail: Bestätigungslink"),
]

RESULT_PLACEHOLDERS = {"runden", "spende", "summe_gesamt", "strecke_km", "paypal_link"}
