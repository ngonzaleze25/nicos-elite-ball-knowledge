import sqlite3

import pytest

from app import create_app
from database import get_db
from journal.matches import create_match

def test_database_schema_and_connection_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():


        
        
        db = get_db()

        assert get_db() is db

        for table_name in ("bankroll_transactions", 
                           "matches",
                           "match_odds",
                            "bet_decisions", 
                            "bets",
                            "match_imports",
                        ):
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


def test_api_match_id_cannot_be_linked_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        first_match = create_match(
            "Sevilla", "Valencia", "2026-10-10T20:00"
        )
        second_match = create_match(
            "Betis", "Getafe", "2026-10-11T18:00"
        )
        db = get_db()

        db.execute(
            """
            INSERT INTO match_imports (external_id, match_id, api_status)
            VALUES (?, ?, ?)
            """,
            (700, first_match, "TIMED"),
        )
        db.commit()

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO match_imports (external_id, match_id, api_status)
                VALUES (?, ?, ?)
                """,
                (700, second_match, "TIMED"),
            )
        db.rollback()

        links = db.execute("SELECT * FROM match_imports").fetchall()
        assert len(links) == 1
        assert links[0]["match_id"] == first_match