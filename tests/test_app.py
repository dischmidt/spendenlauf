import io
import re

import pytest
from docx import Document
from PIL import Image

from app import create_app, mailer
from app.util import fmt_euro, fmt_km, parse_euro


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.org")
    monkeypatch.setenv("BASE_URL", "https://spendenlauf.test")
    from app.util import limiter
    limiter._hits.clear()
    application = create_app({"TESTING": True, "TESTING_NO_CSRF": True, "MAIL_ASYNC": False,
                              "SESSION_COOKIE_SECURE": False})
    return application


@pytest.fixture()
def sent(monkeypatch):
    box = []

    def fake_send(to, subject, body, cfg=None, server=None, images=None):
        box.append({"to": to, "subject": subject, "body": body, "images": list(images or [])})

    monkeypatch.setattr(mailer, "send", fake_send)
    monkeypatch.setattr(mailer, "_connect", lambda cfg, *a: _FakeServer())
    return box


class _FakeServer:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def quit(self):
        pass


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, **kw):
    data = {"name": "Oma Inge", "email": "inge@example.de", "betrag": "1,50", "datenschutz": "1"}
    data.update(kw)
    return client.post("/registrieren", data=data, content_type="multipart/form-data")


def confirm_url(mail):
    return re.search(r"https://spendenlauf\.test(/bestaetigen/\S+)", mail["body"]).group(1)


def test_money_helpers():
    assert parse_euro("1,50") == 150
    assert parse_euro("2") == 200
    assert parse_euro("1.234,50 €") == 123450
    with pytest.raises(ValueError):
        parse_euro("1,505")
    assert fmt_euro(123450) == "1.234,50 €"
    assert fmt_km(1400) == "1,4 km"
    assert fmt_km(2000) == "2 km"


def test_register_confirm_and_list(client, sent):
    r = register(client)
    assert r.status_code == 200 and "Fast geschafft" in r.get_data(as_text=True)
    assert "Oma Inge" not in client.get("/").get_data(as_text=True)
    url = confirm_url(sent[-1])
    assert "Danke" in client.get(url).get_data(as_text=True)
    page = client.get("/").get_data(as_text=True)
    assert "Oma Inge" in page and "1,50 €" in page


def test_confirm_extra_page_when_enabled(app, client, sent):
    with app.app_context():
        from app.settings import save
        save({"bestaetigungsseite": "1"})
    register(client)
    url = confirm_url(sent[-1])
    assert "Zusage bestätigen" in client.get(url).get_data(as_text=True)
    assert "Oma Inge" not in client.get("/").get_data(as_text=True)
    assert "Danke" in client.post(url).get_data(as_text=True)
    assert "Oma Inge" in client.get("/").get_data(as_text=True)


def test_validation_errors(client, sent):
    r = register(client, betrag="abc", email="kaputt", hoechst="0,50", datenschutz="")
    assert r.status_code == 400
    text = r.get_data(as_text=True)
    assert "gültige E-Mail" in text and "Datenschutzhinweis" in text and not sent


def test_anonymous_and_image(client, sent):
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), "red").save(buf, "PNG")
    buf.seek(0)
    register(client, name="Bäckerei Meyer", email="b@example.de", betrag="2", bild=(buf, "logo.png"))
    client.post(confirm_url(sent[-1]))
    register(client, name="Geheim", email="g@example.de", betrag="3", anonym="1")
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert "Geheim" not in page and "Anonym" in page
    assert page.index("Anonym") < page.index("Bäckerei Meyer")  # 3 € vor 2 €
    assert re.search(r'/bild/s-[0-9a-f]+\.jpg', page)


def test_duplicate_email_sends_already_mail(client, sent):
    register(client)
    client.post(confirm_url(sent[-1]))
    register(client, betrag="5")
    assert sent[-1]["subject"] == "Du bist schon dabei"


def test_result_mode_cap_and_card(client, app, sent):
    register(client, hoechst="10", quittung="1", quittung_name="Inge M.", strasse="Weg 1", plz_ort="44867 Bochum")
    client.post(confirm_url(sent[-1]))
    client.post("/admin/sponsoren/neu", data={"name": "Opa Kurt", "betrag": "0,50"})
    client.post("/admin/lauf", data={"action": "runden", "runden": "12"})
    client.post("/admin/lauf", data={"action": "phase", "phase": "ergebnis"})
    page = client.get("/").get_data(as_text=True)
    assert "16,00 €" in page          # 10,00 (gedeckelt statt 18,00) + 6,00
    assert "1,2 km" in page
    assert 'name="betrag"' not in page  # Registrierung geschlossen

    r = client.get("/admin/karte.docx")
    doc = Document(io.BytesIO(r.data))
    head = doc.tables[0].rows[0].cells
    assert "2a" in head[0].text and "Max Mustermann" in head[0].text and "12" in head[1].text
    rows = doc.tables[1].rows
    assert "(100m)" in rows[0].cells[0].text
    assert rows[1].cells[1].text == "Oma Inge" and rows[1].cells[2].text == "Opt-In per Email-Bestätigung"
    assert rows[1].cells[3].text == "10,00 €" and "44867 Bochum" in rows[1].cells[4].text
    assert rows[2].cells[1].text == "Opa Kurt" and rows[2].cells[2].text == ""


def test_card_adds_rows(client):
    for i in range(7):
        client.post("/admin/sponsoren/neu", data={"name": f"Sponsor {i}", "betrag": "1"})
    doc = Document(io.BytesIO(client.get("/admin/karte.docx").data))
    assert len(doc.tables[1].rows) == 8


def test_payment_and_rundmail(client, app, sent):
    register(client)
    client.post(confirm_url(sent[-1]))
    client.post("/admin/lauf", data={"action": "runden", "runden": "10"})
    client.post("/admin/sponsoren/1/zahlung", data={"zahlart": "bar"})
    assert "bezahlt" in client.get("/admin/sponsoren?zahlung=bezahlt").get_data(as_text=True)
    with app.app_context():
        from app.settings import save
        save({"paypal_empfaenger": "spenden@example.org"})
    sent.clear()
    r = client.post("/admin/rundmail", data={"action": "senden", "betreff": "Hallo {name}",
                                             "text": "Du zahlst {spende}. {paypal_link}", "anzahl": "1"})
    assert r.status_code == 302
    assert sent[0]["subject"] == "Hallo Oma Inge"
    assert "15,00 €" in sent[0]["body"] and "business=spenden%40example.org" in sent[0]["body"]


# ---------------------------------------------------------------- DE|EN

def test_default_german_without_header(client):
    page = client.get("/").get_data(as_text=True)
    assert 'lang="de"' in page
    assert "Mitmachen" in page


def test_english_via_accept_language_header(client):
    page = client.get("/", headers={"Accept-Language": "en"}).get_data(as_text=True)
    assert 'lang="en"' in page
    assert "Join in" in page


def test_language_cookie_overrides_header_and_persists(client):
    r = client.get("/sprache/en", headers={"Accept-Language": "de"})
    assert r.status_code == 302 and r.headers["Location"] == "/"
    page = client.get("/", headers={"Accept-Language": "de"}).get_data(as_text=True)
    assert 'lang="en"' in page  # Cookie übersteuert den Header
    client.get("/sprache/de")
    page2 = client.get("/", headers={"Accept-Language": "en"}).get_data(as_text=True)
    assert 'lang="de"' in page2


def test_set_language_rejects_external_next(client):
    r = client.get("/sprache/en?next=https://evil.example/")
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
    r2 = client.get("/sprache/de?next=//evil.example/")
    assert r2.headers["Location"] == "/"


def test_set_language_rejects_unknown_lang(client):
    assert client.get("/sprache/fr").status_code == 404


def test_zweck_en_fallback_then_override(app, client):
    page = client.get("/", headers={"Accept-Language": "en"}).get_data(as_text=True)
    assert "Förderverein" in page  # kein zweck_en gesetzt -> deutscher Text als Fallback
    with app.app_context():
        from app.settings import save
        save({"zweck_en": "Proceeds go to the parents association."})
    page2 = client.get("/", headers={"Accept-Language": "en"}).get_data(as_text=True)
    assert "Proceeds go to the parents association." in page2


def test_registration_stores_language_and_sends_english_mail(app, client, sent):
    r = client.post(
        "/registrieren",
        data={"name": "John Doe", "email": "john@example.com", "betrag": "2", "datenschutz": "1"},
        content_type="multipart/form-data", headers={"Accept-Language": "en"},
    )
    assert r.status_code == 200
    with app.app_context():
        from app.db import get_db
        sp = get_db().execute("SELECT sprache FROM sponsor WHERE email = ?", ("john@example.com",)).fetchone()
        assert sp["sprache"] == "en"
    mail = sent[-1]
    assert mail["subject"] == "Please confirm your pledge for Max"
    assert "Hi John Doe" in mail["body"] and "thank you for supporting Max" in mail["body"]


def test_registration_without_header_sends_german_mail(client, sent):
    register(client, name="Deutscher Sponsor", email="de-sponsor@example.com")
    mail = sent[-1]
    assert mail["subject"] == "Bitte bestätige deine Zusage für Max"
    assert "Hallo Deutscher Sponsor" in mail["body"]


def test_admin_sponsor_english_welcome_mail(client, sent):
    r = client.post(
        "/admin/sponsoren/neu",
        data={"name": "Jane Admin", "email": "jane@example.com", "betrag": "1,00",
              "sprache": "en", "willkommen": "1"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 302
    mail = sent[-1]
    assert mail["subject"] == "Thank you for your support, Jane Admin"
    assert "Thank you very much!" in mail["body"]


def test_rundmail_sends_each_recipient_their_own_language(client, sent):
    client.post("/admin/sponsoren/neu", data={"name": "Deutsch Sponsor", "email": "de2@example.com",
                                               "betrag": "1,00", "sprache": "de"}, content_type="multipart/form-data")
    client.post("/admin/sponsoren/neu", data={"name": "English Sponsor", "email": "en2@example.com",
                                               "betrag": "1,00", "sprache": "en"}, content_type="multipart/form-data")
    r = client.post("/admin/rundmail", data={
        "action": "senden", "betreff": "Hallo {name}", "text": "Danke {name}",
        "betreff_en": "Hello {name}", "text_en": "Thanks {name}", "anzahl": "2",
    })
    assert r.status_code == 302
    by_to = {m["to"]: m for m in sent}
    assert by_to["de2@example.com"]["body"] == "Danke Deutsch Sponsor"
    assert by_to["en2@example.com"]["body"] == "Thanks English Sponsor"


def test_rundmail_falls_back_to_german_when_english_empty(client, sent):
    client.post("/admin/sponsoren/neu", data={"name": "English Sponsor", "email": "en3@example.com",
                                               "betrag": "1,00", "sprache": "en"}, content_type="multipart/form-data")
    r = client.post("/admin/rundmail", data={
        "action": "senden", "betreff": "Hallo {name}", "text": "Danke {name}", "anzahl": "1",
    })
    assert r.status_code == 302
    assert sent[-1]["body"] == "Danke English Sponsor"


def test_paypal_me_setting(client, sent):
    client.post("/admin/einstellungen", data={"paypal_me": "maxrennt", "rundenlaenge_m": "100", "max_betrag": "100"})
    register(client)
    client.post(confirm_url(sent[-1]))
    client.post("/admin/lauf", data={"action": "runden", "runden": "2"})
    client.post("/admin/rundmail", data={"action": "senden", "betreff": "x", "text": "{paypal_link}", "anzahl": "1"})
    assert sent[-1]["body"] == "https://paypal.me/maxrennt/3.00EUR"


def test_cancel_overrides(client):
    client.post("/admin/lauf", data={"action": "absage", "abgesagt": "1", "absage_text": "Max ist krank."})
    page = client.get("/").get_data(as_text=True)
    assert "Max ist krank." in page and 'name="betrag"' not in page


def test_settings_change_runner_name(client):
    client.post("/admin/einstellungen", data={"laeufer_name": "Paul", "rundenlaenge_m": "400", "max_betrag": "100"})
    page = client.get("/").get_data(as_text=True)
    assert "Paul läuft für den neuen Schulhof" in page and "400 m" in page


def test_hoechst_default_factor_tight_cap_shows_text(client, sent):
    register(client, betrag="2,00", hoechst="15")
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert "höchstens 15,00 €" in page
    assert "*)" not in page


def test_hoechst_default_factor_loose_cap_shows_footnote(client, sent):
    register(client, betrag="2,00", hoechst="25")
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert "höchstens 25,00 €" not in page
    assert "*)" in page
    assert "zusätzlich ein Höchstbetrag vereinbart" in page


def test_hoechst_faktor_admin_adjustable(client, sent):
    client.post("/admin/einstellungen", data={"hoechst_faktor": "20", "rundenlaenge_m": "100", "max_betrag": "100"})
    register(client, betrag="2,00", hoechst="25")
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert "höchstens 25,00 €" in page  # 25 < 20 x 2 = 40 -> jetzt "show"


def test_hoechst_footnote_on_confirm_page(app, client, sent):
    with app.app_context():
        from app.settings import save
        save({"bestaetigungsseite": "1"})
    register(client, betrag="2,00", hoechst="25")
    url = confirm_url(sent[-1])
    page = client.get(url).get_data(as_text=True)
    assert "*)" in page
    assert "höchstens 25,00 €" not in page
    assert "zusätzlich ein Höchstbetrag vereinbart" in page


def test_sort_default_is_datum_absteigend(client, sent):
    register(client, name="Zuerst", email="zuerst@example.de")
    client.post(confirm_url(sent[-1]))
    register(client, name="Danach", email="danach@example.de")
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert page.index("Danach") < page.index("Zuerst")  # jüngste Bestätigung zuerst


def test_sort_by_name_aufsteigend(client, sent):
    client.post("/admin/einstellungen", data={"sponsor_sort_feld": "name", "sponsor_sort_richtung": "auf",
                                               "rundenlaenge_m": "100", "max_betrag": "100"})
    register(client, name="Zoe", email="zoe@example.de")
    client.post(confirm_url(sent[-1]))
    register(client, name="Anna", email="anna@example.de")
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert page.index("Anna") < page.index("Zoe")


def test_sort_by_betrag_absteigend(client, sent):
    client.post("/admin/einstellungen", data={"sponsor_sort_feld": "betrag", "sponsor_sort_richtung": "ab",
                                               "rundenlaenge_m": "100", "max_betrag": "100"})
    register(client, name="Klein", email="klein@example.de", betrag="1,00")
    client.post(confirm_url(sent[-1]))
    register(client, name="Gross", email="gross@example.de", betrag="5,00")
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert page.index("Gross") < page.index("Klein")


def test_pagination_splits_across_pages(client, sent):
    client.post("/admin/einstellungen", data={"sponsor_pro_seite": "5", "rundenlaenge_m": "100", "max_betrag": "100"})
    for i in range(6):
        client.post("/admin/sponsoren/neu", data={"name": f"Sponsor {i}", "betrag": "1,00"})
    page1 = client.get("/").get_data(as_text=True)
    assert "Seite 1 von 2" in page1
    assert "Weiter" in page1 and "Zurück" not in page1
    assert sum(f"Sponsor {i}" in page1 for i in range(6)) == 5
    page2 = client.get("/?seite=2").get_data(as_text=True)
    assert "Seite 2 von 2" in page2
    assert "Zurück" in page2 and "Weiter" not in page2
    assert sum(f"Sponsor {i}" in page2 for i in range(6)) == 1


def test_pagination_off_shows_all_on_one_page(client, sent):
    client.post("/admin/einstellungen", data={"sponsor_pro_seite": "0", "rundenlaenge_m": "100", "max_betrag": "100"})
    for i in range(3):
        register(client, name=f"Sponsor {i}", email=f"viele{i}@example.de")
        client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert all(f"Sponsor {i}" in page for i in range(3))
    assert "Seite 1 von" not in page


def test_mindestbeitrag_default_rejects_below_020(client, sent):
    r = register(client, betrag="0,10")
    assert r.status_code == 400
    text = r.get_data(as_text=True)
    assert "mindestens 0,20" in text
    assert not sent


def test_mindestbeitrag_default_accepts_exactly_020(client, sent):
    r = register(client, betrag="0,20")
    assert r.status_code == 200
    assert sent


def test_mindestbeitrag_hint_shown_in_form(client):
    page = client.get("/").get_data(as_text=True)
    assert "Mindestens 0,20 €" in page


def test_mindestbeitrag_zero_disables_feature(client, sent):
    client.post("/admin/einstellungen", data={"mindestbeitrag": "0", "rundenlaenge_m": "100", "max_betrag": "100"})
    page = client.get("/").get_data(as_text=True)
    assert "Mindestens" not in page
    r = register(client, betrag="0,01")
    assert r.status_code == 200 and sent
    sent.clear()
    r = register(client, betrag="0", email="null@example.de")
    assert r.status_code == 400
    assert "größer als 0" in r.get_data(as_text=True)
    assert not sent


def test_mindestbeitrag_admin_adjustable(client, sent):
    client.post("/admin/einstellungen", data={"mindestbeitrag": "1,00", "rundenlaenge_m": "100", "max_betrag": "100"})
    r = register(client, betrag="0,50")
    assert r.status_code == 400
    assert "mindestens 1,00" in r.get_data(as_text=True)
    assert not sent


def test_zeitpunkt_default_off(client, sent):
    register(client)
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert "vor " not in page


def test_zeitpunkt_shown_when_enabled(client, sent):
    client.post("/admin/einstellungen", data={"sponsor_zeige_zeitpunkt": "1", "rundenlaenge_m": "100", "max_betrag": "100"})
    register(client)
    client.post(confirm_url(sent[-1]))
    page = client.get("/").get_data(as_text=True)
    assert "vor wenigen Sekunden" in page


def test_zeitpunkt_hour_bucket(app, client, sent):
    client.post("/admin/einstellungen", data={"sponsor_zeige_zeitpunkt": "1", "rundenlaenge_m": "100", "max_betrag": "100"})
    register(client)
    client.post(confirm_url(sent[-1]))
    with app.app_context():
        from datetime import datetime, timedelta, timezone

        from app.db import get_db
        db = get_db()
        vor_3h = (datetime.now(timezone.utc) - timedelta(hours=3, minutes=5)).isoformat(timespec="seconds")
        db.execute("UPDATE sponsor SET bestaetigt_am=? WHERE email=?", (vor_3h, "inge@example.de"))
        db.commit()
    page = client.get("/").get_data(as_text=True)
    assert "vor 3 Stunden" in page


def test_zeitpunkt_absolute_date_in_ergebnis_phase(app, client, sent):
    client.post("/admin/einstellungen", data={"sponsor_zeige_zeitpunkt": "1", "rundenlaenge_m": "100", "max_betrag": "100"})
    register(client)
    client.post(confirm_url(sent[-1]))
    with app.app_context():
        from app.db import get_db
        db = get_db()
        db.execute("UPDATE sponsor SET bestaetigt_am=? WHERE email=?",
                   ("2026-01-02T10:00:00+00:00", "inge@example.de"))
        db.commit()
    client.post("/admin/lauf", data={"action": "phase", "phase": "ergebnis"})
    page = client.get("/").get_data(as_text=True)
    assert "02.01.2026" in page
    assert "vor " not in page


def test_footer_text_default(client):
    page = client.get("/").get_data(as_text=True)
    assert "Sponsorenlauf der Musterschule am 25.09.2026." in page
    assert "Der Erlös geht an den Förderverein der Schule." in page


def test_footer_text_admin_editable_with_placeholders(client):
    client.post("/admin/einstellungen", data={
        "footer_text": "{schule} läuft am {lauf_datum} für den guten Zweck.",
        "rundenlaenge_m": "100", "max_betrag": "100",
    })
    page = client.get("/").get_data(as_text=True)
    assert "Musterschule läuft am 25.09.2026 für den guten Zweck." in page


def test_footer_text_en_fallback_then_override(client):
    page = client.get("/", headers={"Accept-Language": "en"}).get_data(as_text=True)
    assert "Der Erlös geht an den Förderverein der Schule." in page  # kein footer_text_en -> Fallback Deutsch
    client.post("/admin/einstellungen", data={
        "footer_text_en": "Sponsored run of {schule} on {lauf_datum}.",
        "rundenlaenge_m": "100", "max_betrag": "100",
    })
    page2 = client.get("/", headers={"Accept-Language": "en"}).get_data(as_text=True)
    assert "Sponsored run of Musterschule on 25.09.2026." in page2


def test_csrf_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app({"TESTING": True, "MAIL_ASYNC": False, "SESSION_COOKIE_SECURE": False})
    r = app.test_client().post("/registrieren", data={"name": "x"})
    assert r.status_code == 400


# ---------------------------------------------------------------- Mailserver

SMTP_FORM = {"smtp_host": "smtp.example.org", "smtp_port": "587", "smtp_security": "starttls",
             "smtp_user": "u@example.org", "mail_from": "u@example.org", "mail_from_name": "Max",
             "mail_reply_to": "", "mail_rate_seconds": "1"}
AJAX = {"X-Requested-With": "fetch"}


def _settings(app):
    from app.settings import load
    with app.app_context():
        return load()


def test_smtp_save_ajax_keeps_templates_and_password(app, client):
    with app.app_context():
        from app.settings import save
        save({"tpl_welcome_subject": "Eigener Betreff", "smtp_password": "alt"})
    r = client.post("/admin/mailserver", data=SMTP_FORM, headers=AJAX)
    assert r.get_json()["ok"] is True
    s = _settings(app)
    assert s["smtp_host"] == "smtp.example.org"
    assert s["smtp_password"] == "alt"  # leeres Feld behält das gespeicherte Passwort
    assert s["tpl_welcome_subject"] == "Eigener Betreff"
    client.post("/admin/mailserver", data={**SMTP_FORM, "smtp_password": "neu"}, headers=AJAX)
    assert _settings(app)["smtp_password"] == "neu"


def test_smtp_save_validates(client):
    r = client.post("/admin/mailserver", data={**SMTP_FORM, "smtp_port": "abc"}, headers=AJAX)
    assert r.get_json()["ok"] is False


def test_template_save_leaves_smtp_alone(app, client):
    with app.app_context():
        from app.settings import save
        save({"smtp_host": "bleibt.example.org"})
    client.post("/admin/mail-einstellungen", data={"tpl_welcome_subject": "Hallo"})
    s = _settings(app)
    assert s["smtp_host"] == "bleibt.example.org"
    assert s["tpl_welcome_subject"] == "Hallo"


def test_smtp_test_uses_unsaved_form_password(app, client, monkeypatch):
    seen = {}

    def fake_test(cfg, to=None):
        seen.update(cfg=cfg, to=to)
        return (465, "ssl"), ["Port 465 mit SSL: erfolgreich"]

    monkeypatch.setattr(mailer, "smtp_test", fake_test)
    r = client.post("/admin/testmail", data={**SMTP_FORM, "smtp_password": "getippt", "test_to": "t@example.org"},
                    headers=AJAX)
    data = r.get_json()
    assert data["ok"] and data["smtp_port"] == "465" and data["smtp_security"] == "ssl"
    assert seen["cfg"]["smtp_password"] == "getippt" and seen["to"] == "t@example.org"
    s = _settings(app)
    assert (s["smtp_password"], s["smtp_port"], s["smtp_security"]) == ("getippt", "465", "ssl")


def test_smtp_test_failure_saves_nothing(app, client, monkeypatch):
    monkeypatch.setattr(mailer, "smtp_test", lambda cfg, to=None: (None, ["Port 587 mit STARTTLS: abgelehnt"]))
    r = client.post("/admin/smtp-test", data={**SMTP_FORM, "smtp_password": "falsch"}, headers=AJAX)
    assert r.get_json()["ok"] is False and r.get_json()["log"]
    assert _settings(app)["smtp_password"] != "falsch"


class _AuthServer:
    """Simuliert einen SMTP-Server, der AUTH PLAIN anbietet."""

    def __init__(self, *a, **kw):
        self.esmtp_features = {"auth": "PLAIN LOGIN"}
        self.cmds = []
        self.closed = False

    def ehlo_or_helo_if_needed(self):
        pass

    def docmd(self, cmd, args=""):
        self.cmds.append((cmd, args))
        return 235, b"ok"

    def login(self, user, password):
        (user + password).encode("ascii")  # verhält sich wie smtplib

    def close(self):
        self.closed = True


def test_login_with_non_ascii_password():
    import base64
    srv = _AuthServer()
    mailer._login(srv, "u@example.org", "Pässwört€")
    cmd, args = srv.cmds[0]
    assert cmd == "AUTH" and args.startswith("PLAIN ")
    assert base64.b64decode(args[6:]).decode("utf-8") == "\0u@example.org\0Pässwört€"


def test_smtp_test_stops_after_auth_failure(monkeypatch):
    import smtplib
    calls = []

    def fail(cfg, port=None, security=None):
        calls.append((port, security))
        raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Error: authentication failed")

    monkeypatch.setattr(mailer, "_connect", fail)
    variant, log = mailer.smtp_test({"smtp_port": "587", "smtp_security": "starttls"})
    assert variant is None and len(calls) == 1
    assert "535" in log[0] and "Passwort" in log[0]


def test_connection_test_sends_no_mail(client, monkeypatch):
    seen = {}

    def fake_test(cfg, to=None):
        seen["to"] = to
        return (587, "starttls"), ["Port 587 mit STARTTLS: erfolgreich"]

    monkeypatch.setattr(mailer, "smtp_test", fake_test)
    r = client.post("/admin/smtp-test", data={**SMTP_FORM, "test_to": "t@example.org"}, headers=AJAX)
    assert r.get_json()["ok"] and seen["to"] is None


def test_testmail_requires_address(client, monkeypatch):
    monkeypatch.setattr(mailer, "smtp_test", lambda cfg, to=None: pytest.fail("darf nicht aufgerufen werden"))
    r = client.post("/admin/testmail", data={**SMTP_FORM, "test_to": ""}, headers=AJAX)
    assert r.get_json()["ok"] is False
    r = client.post("/admin/testmail", data={**SMTP_FORM, "test_to": "kaputt"}, headers=AJAX)
    assert r.get_json()["ok"] is False


# ---------------------------------------------------------------- Countdown und Laufuhr

def _settings(app):
    from app.db import connect
    from app.settings import load

    con = connect(app.config["DATABASE"])
    try:
        return load(con)
    finally:
        con.close()


def _ziel_ms(html):
    m = re.search(r'data-clock-ziel="(\d+)"', html)
    return int(m.group(1)) if m else None


def test_countdown_shows_start_time_and_can_be_disabled(app, client):
    from datetime import datetime
    from app.util import BERLIN

    html = client.get("/").get_data(as_text=True)
    expected = int(datetime(2026, 9, 25, 10, 45, tzinfo=BERLIN).timestamp() * 1000)
    assert _ziel_ms(html) == expected
    assert "Start in" in html
    assert "data-live=" in html  # Countdown aktualisiert sich, damit Besucher den Start sehen

    client.post("/admin/lauf", data={"action": "uhr", "start_zeit": "2026-09-25T10:45",
                                     "dauer_min": "10", "dauer_sek": "0"})
    html = client.get("/").get_data(as_text=True)
    assert _ziel_ms(html) is None


def test_countdown_blinks_at_zero(app, client):
    client.post("/admin/lauf", data={"action": "uhr", "start_zeit": "2020-01-01T10:00", "countdown_aktiv": "1",
                                     "dauer_min": "10", "dauer_sek": "0"})
    html = client.get("/").get_data(as_text=True)
    assert "clock--null" in html
    assert ">00:00</time>" in html


def test_uhr_settings_validation(app, client):
    client.post("/admin/lauf", data={"action": "uhr", "start_zeit": "quatsch", "countdown_aktiv": "1",
                                     "dauer_min": "7", "dauer_sek": "30"})
    s = _settings(app)
    assert s["start_zeit"] == "2026-09-25T10:45"
    assert s["laufdauer_s"] == "450"


def test_start_button_starts_run_clock(app, client):
    from app.util import parse_iso

    client.post("/admin/lauf", data={"action": "start"})
    s = _settings(app)
    assert s["live_aktiv"] == "1" and s["lauf_gestartet_am"]
    html = client.get("/").get_data(as_text=True)
    start_ms = int(parse_iso(s["lauf_gestartet_am"]).timestamp() * 1000)
    assert _ziel_ms(html) == start_ms + 600_000
    assert "Noch zu laufen" in html
    # zweiter Klick überschreibt den Start nicht
    client.post("/admin/lauf", data={"action": "start"})
    assert _settings(app)["lauf_gestartet_am"] == s["lauf_gestartet_am"]
    client.post("/admin/lauf", data={"action": "start_reset"})
    assert _settings(app)["lauf_gestartet_am"] == ""


def test_switching_to_live_starts_clock_once(app, client):
    client.post("/admin/lauf", data={"action": "phase", "phase": "sammeln", "live_aktiv": "1"})
    first = _settings(app)["lauf_gestartet_am"]
    assert first
    client.post("/admin/lauf", data={"action": "phase", "phase": "sammeln", "live_aktiv": "1"})
    assert _settings(app)["lauf_gestartet_am"] == first
    frag = client.get("/teil/live").get_data(as_text=True)
    assert 'data-part="clock"' in frag and 'data-mode="live"' in frag


def test_ergebnis_shows_result_instead_of_clock(app, client):
    client.post("/admin/lauf", data={"action": "start"})
    client.post("/admin/lauf", data={"action": "runden", "runden": "23"})
    client.post("/admin/lauf", data={"action": "phase", "phase": "ergebnis"})
    html = client.get("/").get_data(as_text=True)
    assert "Geschafft!" in html and "23 Runden" in html
    assert _ziel_ms(html) is None


def test_fmt_rest():
    from app.logic import fmt_rest

    assert fmt_rest(0) == "00:00"
    assert fmt_rest(600) == "10:00"
    assert fmt_rest(3661) == "01:01:01"
    assert fmt_rest(90061) == "1 Tage 01:01:01"



# ---------------------------------------------------------------- Start-Mail und Bilder in Vorlagen

def _png():
    buf = io.BytesIO()
    Image.new("RGBA", (1600, 800), (200, 30, 30, 255)).save(buf, "PNG")
    buf.seek(0)
    return buf


def _confirmed_sponsor(client, sent, **kw):
    register(client, **kw)
    client.get(confirm_url(sent[-1]))


def test_template_images_upload_public_and_in_mail(app, client, sent):
    r = client.post("/admin/mail-einstellungen", data={"tpl_welcome_bild_neu": (_png(), "bild.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    namen = _settings(app)["tpl_welcome_bilder"].split()
    assert len(namen) == 1 and namen[0].startswith("m-")
    img = client.get(f"/bild/{namen[0]}")
    assert img.status_code == 200 and img.mimetype == "image/jpeg"
    assert max(Image.open(io.BytesIO(img.data)).size) == 1200

    client.post("/admin/sponsoren/neu", data={"name": "Opa", "email": "opa@example.de", "betrag": "1",
                                              "willkommen": "1"})
    assert sent[-1]["images"] == [f"https://spendenlauf.test/bild/{namen[0]}"]

    client.post("/admin/mail-einstellungen", data={"tpl_welcome_bild_weg": namen[0]})
    assert _settings(app)["tpl_welcome_bilder"] == ""


def test_build_message_contains_images():
    msg = mailer.build_message({"mail_from": "a@example.org"}, "b@example.org", "Hi", "Text",
                               ["https://x.test/bild/m-1.jpg"])
    html = msg.get_body(("html",)).get_content()
    assert '<img src="https://x.test/bild/m-1.jpg"' in html
    assert "https://x.test/bild/m-1.jpg" in msg.get_body(("plain",)).get_content()


def test_start_sends_start_mail_when_enabled(app, client, sent):
    _confirmed_sponsor(client, sent)
    client.post("/admin/mail-einstellungen", data={"start_mail_formular": "1", "start_mail_aktiv": "1",
                                                   "tpl_start_bild_neu": (_png(), "s.png")},
                content_type="multipart/form-data")
    n = len(sent)
    client.post("/admin/lauf", data={"action": "start"})
    start_mails = sent[n:]
    assert len(start_mails) == 1
    assert start_mails[0]["subject"] == "Max ist gestartet!"
    assert len(start_mails[0]["images"]) == 1
    # kein zweiter Versand beim erneuten Klick
    client.post("/admin/lauf", data={"action": "start"})
    assert len(sent) == n + 1


def test_start_without_checkbox_sends_nothing(app, client, sent):
    _confirmed_sponsor(client, sent)
    n = len(sent)
    client.post("/admin/lauf", data={"action": "phase", "phase": "sammeln", "live_aktiv": "1"})
    assert len(sent) == n
    assert _settings(app)["lauf_gestartet_am"]


def test_rundmail_vorlage_start_takes_images(app, client, sent):
    _confirmed_sponsor(client, sent)
    client.post("/admin/mail-einstellungen", data={"tpl_start_bild_neu": (_png(), "s.png")},
                content_type="multipart/form-data")
    name = _settings(app)["tpl_start_bilder"].strip()
    html = client.post("/admin/rundmail", data={"action": "vorlage_start"}).get_data(as_text=True)
    assert f'value="{name}"' in html and f"/bild/{name}" in html


# ---------------------------------------------------------------- Vorläufiges Ergebnis und Auf die Plätze

def _lauf_vorbei(app, minuten=2):
    from datetime import datetime, timedelta, timezone

    from app.settings import save

    start = datetime.now(timezone.utc) - timedelta(seconds=600 + minuten * 60)
    with app.app_context():
        save({"lauf_gestartet_am": start.isoformat()})


def test_ende_mail_after_run_clock_expired(app, client, sent):
    _confirmed_sponsor(client, sent)
    client.post("/admin/mail-einstellungen", data={"start_mail_formular": "1", "ende_mail_aktiv": "1"})
    client.post("/admin/lauf", data={"action": "start"})
    client.post("/admin/lauf", data={"action": "runden", "runden": "17"})
    n = len(sent)
    client.get("/admin/lauf")  # Laufuhr läuft noch
    assert len(sent) == n
    _lauf_vorbei(app)
    client.get("/teil/live")
    assert len(sent) == n + 1
    assert sent[-1]["subject"] == "Geschafft! Max ist 17 Runden gelaufen (vorläufig)"
    assert "17 Runden" in sent[-1]["body"] and "25,50 €" in sent[-1]["body"]
    assert _settings(app)["ende_mail_gesendet_am"]
    # nur einmal pro Start
    client.get("/admin/lauf")
    client.get("/")
    assert len(sent) == n + 1
    # Zurücksetzen und neu starten macht sie wieder fällig
    client.post("/admin/lauf", data={"action": "start_reset"})
    assert _settings(app)["ende_mail_gesendet_am"] == ""


def test_ende_mail_not_sent_when_disabled_or_stale_or_ergebnis(app, client, sent):
    _confirmed_sponsor(client, sent)
    client.post("/admin/lauf", data={"action": "start"})
    n = len(sent)
    _lauf_vorbei(app)
    client.get("/admin/lauf")
    assert len(sent) == n  # Haken nicht gesetzt
    client.post("/admin/mail-einstellungen", data={"start_mail_formular": "1", "ende_mail_aktiv": "1"})
    _lauf_vorbei(app, minuten=120)
    client.get("/admin/lauf")
    assert len(sent) == n  # Ende zu lange her
    _lauf_vorbei(app)
    client.post("/admin/lauf", data={"action": "phase", "phase": "ergebnis", "live_aktiv": "1"})
    client.get("/admin/lauf")
    assert len(sent) == n  # schon im Ergebnis


def test_ende_button_saves_end_and_sends_mail_immediately(app, client, sent):
    _confirmed_sponsor(client, sent)
    html = client.get("/admin/lauf").get_data(as_text=True)
    assert "Startzeit speichern" in html and "Startzeit und Uhr speichern" not in html
    assert "Endzeit und vorläufige Rundenzahl speichern" in html
    client.post("/admin/lauf", data={"action": "start"})
    n = len(sent)
    # ausgeschaltet: speichert, sendet aber nicht
    client.post("/admin/lauf", data={"action": "ende", "ende_zeit": "2026-09-25T10:57", "runden": "12"})
    s = _settings(app)
    assert s["ende_zeit"] == "2026-09-25T10:57" and s["runden"] == "12"
    assert len(sent) == n and s["ende_mail_gesendet_am"] == ""
    # eingeschaltet: sofort, ohne auf die Laufuhr zu warten
    client.post("/admin/mail-einstellungen", data={"start_mail_formular": "1", "ende_mail_aktiv": "1"})
    client.post("/admin/lauf", data={"action": "ende", "ende_zeit": "", "runden": "17"})
    assert len(sent) == n + 1
    assert sent[-1]["subject"] == "Geschafft! Max ist 17 Runden gelaufen (vorläufig)"
    s = _settings(app)
    assert s["ende_mail_gesendet_am"] and s["ende_zeit"]
    # nur einmal pro Lauf, auch nicht nachträglich über die Laufuhr
    client.post("/admin/lauf", data={"action": "ende", "ende_zeit": "", "runden": "18"})
    _lauf_vorbei(app)
    client.get("/teil/live")
    assert len(sent) == n + 1 and _settings(app)["runden"] == "18"
    # Neustart setzt Endzeit und Versandmarke zurück
    client.post("/admin/lauf", data={"action": "start_reset"})
    s = _settings(app)
    assert s["ende_zeit"] == "" and s["ende_mail_gesendet_am"] == ""


def test_new_templates_in_settings_and_rundmail(app, client, sent):
    html = client.get("/admin/mail-einstellungen").get_data(as_text=True)
    assert (html.index("<legend>Rundmail: Auf die Plätze</legend>") < html.index("<legend>Start</legend>")
            < html.index("<legend>Vorläufiges Ergebnis</legend>"))
    assert 'data-tpl-tab="vorlaeufig"' in html and 'data-tpl-panel="vorlaeufig"' in html
    assert 'name="ende_mail_aktiv"' in html
    _confirmed_sponsor(client, sent)
    html = client.post("/admin/rundmail", data={"action": "vorlage_plaetze"}).get_data(as_text=True)
    assert "steht am Start" in html


def test_static_urls_carry_version(client):
    html = client.get("/").get_data(as_text=True)
    assert re.search(r'/static/app\.js\?v=\d+"', html) and re.search(r'/static/style\.css\?v=\d+"', html)
    assert client.get(re.search(r'(/static/app\.js\?v=\d+)', html).group(1)).status_code == 200
