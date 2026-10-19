"""Mini-i18n für die öffentliche Seite: feste UI-Texte auf Deutsch/Englisch,
Spracherkennung per Cookie/Accept-Language. Admin-pflegbare Freitexte werden
separat über settings.localize() behandelt."""
from flask import g, request

LANGS = ("de", "en")

STRINGS = {
    # Kopfzeile / Navigation
    "skip": {"de": "Zum Inhalt springen", "en": "Skip to content"},
    "menu": {"de": "Menü", "en": "Menu"},
    "nav.mitmachen": {"de": "Mitmachen", "en": "Join in"},
    "nav.sponsoren": {"de": "Sponsoren", "en": "Sponsors"},
    "legal.impressum_title": {"de": "Impressum", "en": "Imprint"},
    "legal.datenschutz_title": {"de": "Datenschutz", "en": "Privacy policy"},
    "meta.og_description": {"de": "Sponsorenlauf am {datum} – {zweck}", "en": "Sponsored run on {datum} – {zweck}"},

    # Registrierungsformular (index.html)
    "form.name_label": {"de": "Dein Name", "en": "Your name"},
    "form.email_label": {"de": "E-Mail-Adresse", "en": "Email address"},
    "form.email_hint": {"de": "Wird nie veröffentlicht.", "en": "Will never be published."},
    "form.betrag_label": {"de": "Betrag pro Runde", "en": "Amount per lap"},
    "form.hoechst_label": {"de": "Höchstbetrag", "en": "Maximum amount"},
    "form.runde_hint": {"de": "Eine Runde ist {m} m lang.", "en": "One lap is {m} m long."},
    "form.hoechst_hint": {
        "de": "Mehr zahlst du nie, egal wie viele Runden es werden.",
        "en": "You'll never pay more, no matter how many laps.",
    },
    "form.hoechst_placeholder": {"de": "z. B. 30", "en": "e.g. 30"},
    "form.mindest_hint": {"de": "Mindestens {betrag} pro Runde.", "en": "At least {betrag} per lap."},
    "form.anonym_label": {
        "de": "Anonym unterstützen – Name und Bild erscheinen nicht in der Liste",
        "en": "Support anonymously – name and photo won't appear in the list",
    },
    "form.bild_label": {"de": "Foto oder Logo", "en": "Photo or logo"},
    "form.bild_hint": {
        "de": "Wird quadratisch zugeschnitten. Bitte nur eigene Bilder.",
        "en": "Will be cropped square. Please use only your own images.",
    },
    "form.quittung_label": {
        "de": "Ich möchte eine Spendenquittung vom Förderverein",
        "en": "I'd like a donation receipt from the parents' association",
    },
    "form.quittung_legend": {"de": "Angaben für die Quittung", "en": "Details for the receipt"},
    "form.strasse_label": {"de": "Straße und Hausnummer", "en": "Street and house number"},
    "form.plz_label": {"de": "PLZ und Ort", "en": "Postal code and city"},
    "form.datenschutz_label": {
        "de": "Ich habe den {link} gelesen.",
        "en": "I have read the {link}.",
    },
    "form.datenschutz_link": {"de": "Datenschutzhinweis", "en": "privacy notice"},
    "form.submit": {"de": "Zusage abschicken", "en": "Submit pledge"},
    "form.errors_alert": {"de": "Bitte prüfe die markierten Felder.", "en": "Please check the marked fields."},
    "ablauf.heading": {"de": "So läuft es ab", "en": "How it works"},
    "join.heading": {"de": "Mitmachen", "en": "Join in"},
    "join.hint": {
        "de": "Du bekommst eine Mail mit einem Bestätigungslink. Erst danach erscheinst du in der Liste.",
        "en": "You'll get an email with a confirmation link. You'll only appear in the list afterwards.",
    },
    "list.heading": {"de": "Sponsoren", "en": "Sponsors"},
    "list.heading_cancel": {"de": "Danke an alle Sponsoren", "en": "Thanks to all sponsors"},
    "share.button": {"de": "Seite teilen", "en": "Share page"},
    "share.copied": {"de": "Link kopiert", "en": "Link copied"},

    # Bestätigungsseite (confirm.html, nur wenn eingeschaltet)
    "confirm.title": {"de": "Zusage bestätigen", "en": "Confirm pledge"},
    "confirm.hello": {
        "de": "Hallo {name}, du unterstützt {laeufer} mit",
        "en": "Hello {name}, you're supporting {laeufer} with",
    },
    "confirm.pro_runde": {"de": "pro Runde", "en": "per lap"},
    "confirm.hoechstens": {"de": "höchstens {betrag}", "en": "max. {betrag}"},
    "confirm.button": {"de": "Zusage bestätigen", "en": "Confirm pledge"},

    # message.html
    "msg.check_mail_h1": {"de": "Fast geschafft", "en": "Almost there"},
    "msg.check_mail_p": {
        "de": "Bitte bestätige deine Zusage über den Link in der E-Mail, die wir dir gerade geschickt "
              "haben. Schau auch im Spam-Ordner nach.",
        "en": "Please confirm your pledge using the link in the email we just sent you. Check your "
              "spam folder too.",
    },
    "common.back_home": {"de": "Zurück zur Startseite", "en": "Back to the homepage"},
    "msg.confirmed_h1": {"de": "Danke, {name}!", "en": "Thank you, {name}!"},
    "msg.confirmed_p": {
        "de": "Deine Zusage ist bestätigt. Nach dem Lauf bekommst du eine Mail mit dem Ergebnis und "
              "deinem Betrag.",
        "en": "Your pledge is confirmed. After the run you'll get an email with the result and your amount.",
    },
    "common.to_sponsor_list": {"de": "Zur Sponsorenliste", "en": "View the sponsor list"},
    "msg.already_h1": {"de": "Schon bestätigt", "en": "Already confirmed"},
    "msg.already_p": {"de": "Deine Zusage ist bereits bestätigt. Danke!", "en": "Your pledge is already confirmed. Thank you!"},
    "msg.expired_h1": {"de": "Der Link ist abgelaufen", "en": "The link has expired"},
    "msg.invalid_h1": {"de": "Der Link ist ungültig", "en": "The link is invalid"},
    "msg.resend_p": {
        "de": "Gib deine E-Mail-Adresse ein, dann schicken wir dir einen neuen Bestätigungslink.",
        "en": "Enter your email address and we'll send you a new confirmation link.",
    },
    "msg.resend_button": {"de": "Neuen Link senden", "en": "Send new link"},
    "msg.too_many_h1": {"de": "Zu viele Versuche", "en": "Too many attempts"},
    "msg.too_many_p": {
        "de": "Von deinem Anschluss kamen in der letzten Stunde zu viele Anfragen. Bitte versuche es "
              "später noch einmal.",
        "en": "Too many requests came from your connection in the last hour. Please try again later.",
    },
    "msg.too_large_h1": {"de": "Das Bild ist zu groß", "en": "The image is too large"},
    "msg.too_large_p": {
        "de": "Bitte wähle ein Bild unter 8 MB oder melde dich ohne Bild an.",
        "en": "Please choose an image under 8 MB or register without an image.",
    },
    "msg.back_form": {"de": "Zurück zum Formular", "en": "Back to the form"},
    "msg.error_h1": {"de": "Das hat nicht geklappt", "en": "Something went wrong"},
    "msg.error_default": {"de": "Die Anfrage war ungültig.", "en": "The request was invalid."},
    "common.to_home": {"de": "Zur Startseite", "en": "To the homepage"},

    # _stat.html
    "stat.cancelled": {"de": "Der Lauf findet für {laeufer} nicht statt.", "en": "The run is not taking place for {laeufer}."},
    "stat.live_label": {"de": "Live – bisher erlaufen", "en": "Live – raised so far"},
    "stat.result_label": {"de": "Ergebnis – erlaufen für den Schulhof", "en": "Result – raised for the schoolyard"},
    "stat.sammeln_label": {"de": "kommen pro Runde zusammen", "en": "pledged per lap"},
    "stat.von": {"de": "von", "en": "from"},

    # _clock.html
    "clock.countdown_label": {"de": "Start in", "en": "Starts in"},
    "clock.lauf_label": {"de": "Noch zu laufen", "en": "Time left"},
    "clock.ergebnis_label": {"de": "Geschafft!", "en": "Done!"},
    "clock.tage": {"de": "Tage", "en": "days"},

    # _list.html
    "list.anonym": {"de": "Anonym", "en": "Anonymous"},
    "list.hoechstens": {"de": "höchstens {betrag}", "en": "max. {betrag}"},
    "list.pro_runde": {"de": "pro Runde", "en": "per lap"},
    "list.empty": {"de": "Noch keine bestätigten Sponsoren.", "en": "No confirmed sponsors yet."},
    "list.be_first": {"de": "Sei die oder der Erste!", "en": "Be the first!"},
    "list.footnote_legend": {
        "de": "*) Für diesen Betrag wurde zusätzlich ein Höchstbetrag vereinbart.",
        "en": "*) An additional maximum amount has been agreed for this amount.",
    },
    "pager.zurueck": {"de": "« Zurück", "en": "« Back"},
    "pager.weiter": {"de": "Weiter »", "en": "Next »"},
    "pager.seite_von": {"de": "Seite {seite} von {seiten}", "en": "Page {seite} of {seiten}"},
    "zeit.gerade_eben": {"de": "vor wenigen Sekunden", "en": "a few seconds ago"},
    "zeit.vor": {"de": "vor {n} {einheit}", "en": "{n} {einheit} ago"},

    # Validierungsfehler im Registrierungsformular (index.html)
    "err.name": {"de": "Bitte gib einen Namen mit 2 bis 80 Zeichen an.", "en": "Please enter a name with 2 to 80 characters."},
    "err.email": {"de": "Bitte gib eine gültige E-Mail-Adresse an.", "en": "Please enter a valid email address."},
    "err.betrag_min": {"de": "Der Betrag pro Runde muss mindestens {betrag} sein.", "en": "The amount per lap must be at least {betrag}."},
    "err.betrag_positive": {"de": "Bitte einen Betrag größer als 0 angeben.", "en": "Please enter an amount greater than 0."},
    "err.betrag_max": {"de": "Bitte höchstens {betrag} pro Runde angeben.", "en": "Please enter at most {betrag} per lap."},
    "err.betrag_format": {
        "de": "Bitte einen Betrag wie 1,50 angeben (höchstens zwei Nachkommastellen).",
        "en": "Please enter an amount like 1.50 (at most two decimal places).",
    },
    "err.hoechst_min": {
        "de": "Der Höchstbetrag muss mindestens so hoch sein wie der Betrag pro Runde.",
        "en": "The maximum amount must be at least as high as the amount per lap.",
    },
    "err.hoechst_format": {
        "de": "Bitte einen Betrag wie 30 oder 30,00 angeben – oder das Feld leer lassen.",
        "en": "Please enter an amount like 30 or 30.00 – or leave the field empty.",
    },
    "err.quittung_name": {"de": "Bitte den Namen für die Quittung angeben.", "en": "Please enter the name for the receipt."},
    "err.strasse": {"de": "Bitte Straße und Hausnummer angeben.", "en": "Please enter street and house number."},
    "err.plz_ort": {"de": "Bitte PLZ und Ort angeben.", "en": "Please enter postal code and city."},
    "err.datenschutz": {
        "de": "Bitte bestätige, dass du den Datenschutzhinweis gelesen hast.",
        "en": "Please confirm that you have read the privacy notice.",
    },
}

PLURALS = {
    "unit.runde": {"de": ("Runde", "Runden"), "en": ("lap", "laps")},
    "unit.sponsor": {"de": ("Sponsor", "Sponsoren"), "en": ("sponsor", "sponsors")},
    "zeit.minute": {"de": ("Minute", "Minuten"), "en": ("minute", "minutes")},
    "zeit.stunde": {"de": ("Stunde", "Stunden"), "en": ("hour", "hours")},
    "zeit.tag": {"de": ("Tag", "Tage"), "en": ("day", "days")},
}


def t(key, **kwargs):
    lang = getattr(g, "lang", "de")
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get("de") or key
    return text.format(**kwargs) if kwargs else text


def tn(key, n, **kwargs):
    lang = getattr(g, "lang", "de")
    forms = PLURALS.get(key, {})
    pair = forms.get(lang) or forms.get("de") or (key, key)
    text = pair[0] if n == 1 else pair[1]
    return text.format(n=n, **kwargs) if kwargs else text


def resolve_lang():
    cookie = request.cookies.get("lang")
    if cookie in LANGS:
        return cookie
    return request.accept_languages.best_match(LANGS, default="de")


def init_app(app):
    @app.before_request
    def _set_lang():
        g.lang = resolve_lang()

    app.jinja_env.globals.update(t=t, tn=tn, LANGS=LANGS)
