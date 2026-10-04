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

        for table_name in ("bankroll_transactions", "matches", "match_odds", "bet_decisions"):
            table = db.execute(
                "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
                ("table", table_name),
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

def test_database_rejects_odds_for_missing_match(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        db = get_db()

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute(
                """
                INSERT INTO match_odds
                    (match_id, bookmaker, home_odds, draw_odds, away_odds)
                VALUES (?, ?, ?, ?, ?)
                """,
                (999, "bet365", 2.0, 3.0, 4.0),
            )

        db.rollback()
        assert db.execute("SELECT COUNT(*) FROM match_odds").fetchone()[0] == 0