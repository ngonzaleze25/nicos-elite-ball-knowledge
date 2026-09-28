import sqlite3

import pytest

from app import create_app
from database import get_db


def test_database_schema_and_connection_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        db = get_db()

        assert get_db() is db

        table = db.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", "bankroll_transactions"),
        ).fetchone()
        assert table is not None

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO bankroll_transactions
                    (transaction_type, amount_cents, description)
                VALUES (?, ?, ?)
                """,
                ("stake", 100, "Invalid positive stake"),
            )

    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")