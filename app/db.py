"""SQLite-Zugriff (ohne WAL-Modus, damit die Datei sich einfach sichern und kopieren lässt)."""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS sponsor (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    email            TEXT UNIQUE,
    betrag_cent      INTEGER NOT NULL,
    hoechst_cent     INTEGER,
    anonym           INTEGER NOT NULL DEFAULT 0,
    bild             TEXT,
    quittung         INTEGER NOT NULL DEFAULT 0,
    quittung_name    TEXT,
    strasse          TEXT,
    plz_ort          TEXT,
    status           TEXT NOT NULL DEFAULT 'unbestaetigt',
    token_hash       TEXT,
    token_ablauf     TEXT,
    bestaetigt_am    TEXT,
    bestaetigt_durch TEXT,
    bezahlt_am       TEXT,
    zahlart          TEXT,
    quelle           TEXT NOT NULL DEFAULT 'web',
    notiz            TEXT,
    erstellt_am      TEXT NOT NULL,
    sprache          TEXT NOT NULL DEFAULT 'de'
);
CREATE INDEX IF NOT EXISTS ix_sponsor_token ON sponsor(token_hash);

CREATE TABLE IF NOT EXISTS einstellung (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS runden_protokoll (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit TEXT NOT NULL,
    alt  INTEGER NOT NULL,
    neu  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rundmail (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    betreff       TEXT NOT NULL,
    text          TEXT NOT NULL,
    betreff_en    TEXT NOT NULL DEFAULT '',
    text_en       TEXT NOT NULL DEFAULT '',
    erstellt_am   TEXT NOT NULL,
    gesendet_am   TEXT,
    status        TEXT NOT NULL DEFAULT 'wartet'
);

CREATE TABLE IF NOT EXISTS rundmail_empfaenger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rundmail_id INTEGER NOT NULL REFERENCES rundmail(id) ON DELETE CASCADE,
    sponsor_id  INTEGER REFERENCES sponsor(id) ON DELETE SET NULL,
    email       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'wartet',
    fehler      TEXT,
    zeit        TEXT
);
"""


def connect(path):
    con = sqlite3.connect(path, timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=15000")
    return con


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def _ensure_column(con, table, column, decl):
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db(app):
    con = connect(app.config["DATABASE"])
    try:
        con.executescript(SCHEMA)
        _ensure_column(con, "sponsor", "sprache", "TEXT NOT NULL DEFAULT 'de'")
        _ensure_column(con, "rundmail", "betreff_en", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "rundmail", "text_en", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "rundmail", "bilder", "TEXT NOT NULL DEFAULT ''")
        from .settings import seed

        seed(con)
        con.commit()
    finally:
        con.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    init_db(app)
