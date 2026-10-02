import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row

    return g.db


def init_db():
    db = get_db()
    root = Path(current_app.root_path)

    for relative_path in (
        Path("bankroll") / "schema.sql",
        Path("journal") / "schema.sql",
    ):
        schema_path = root / relative_path
        with schema_path.open(encoding="utf-8") as schema_file:
            db.executescript(schema_file.read())

    _ensure_bet_decision_stake_columns(db)


def _ensure_bet_decision_stake_columns(db):
    existing_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(bet_decisions)").fetchall()
    }
    stake_columns = {
        "full_kelly_stake_cents": (
            "INTEGER NOT NULL DEFAULT 0 "
            "CHECK (full_kelly_stake_cents >= 0)"
        ),
        "quarter_kelly_stake_cents": (
            "INTEGER NOT NULL DEFAULT 0 "
            "CHECK (quarter_kelly_stake_cents >= 0)"
        ),
        "recommended_stake_cents": (
            "INTEGER NOT NULL DEFAULT 0 "
            "CHECK (recommended_stake_cents >= 0)"
        ),
    }

    for column_name, definition in stake_columns.items():
        if column_name not in existing_columns:
            db.execute(
                f"ALTER TABLE bet_decisions ADD COLUMN {column_name} {definition}"
            )


def close_db(error=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
