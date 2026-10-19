"""Sponsorenlauf-App."""
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)

    data_dir = Path(os.environ.get("DATA_DIR", Path(app.root_path).parent / "data"))
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-unsicher-bitte-aendern"),
        DATA_DIR=str(data_dir),
        DATABASE=str(data_dir / os.environ.get("DATABASE_FILE", "spendenlauf.db")),
        UPLOAD_DIR=str(data_dir / "uploads"),
        BASE_URL=os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/"),
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL", "").strip(),
        SOFFICE_BIN=os.environ.get("SOFFICE_BIN", "soffice"),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "1") == "1",
        MAIL_ASYNC=True,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    # Hinter nginx: echte Client-IP und https-Schema übernehmen
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    from . import admin, db, i18n, public, util

    db.init_app(app)
    i18n.init_app(app)
    util.init_app(app)
    app.register_blueprint(public.bp)
    app.register_blueprint(admin.bp)
    return app
