import os
import time
import json
from urllib.request import urlopen

from datetime import datetime, timezone
from contextlib import closing
from flask import Flask,g,request
from pymssql import Error

from services.journal.database import check_database_health, connect_with_retry, get_connection
from services.journal.migrate import run_migrations

def fetch_bankroll_balance():
    base_url = os.environ["BANKROLL_URL"].rstrip("/")
    with urlopen(f"{base_url}/balance", timeout=2) as response:
        return json.load(response)["balance_cents"]


def create_app():
    app = Flask(__name__)

    connection = connect_with_retry()
    try:
        run_migrations(connection)
    finally:
        connection.close()

    @app.before_request
    def start_request_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def log_request(response):
        elapsed_ms = (time.perf_counter() - g.request_started_at) * 1000
        print(
            f"{request.method} {request.path} "
            f"{response.status_code} {elapsed_ms:.1f} ms",
            flush=True,
        )
        return response
    @app.get("/health")
    def health():
        version = os.environ.get("APP_VERSION", "dev")

        try:
            check_database_health()
        except (Error, RuntimeError):
            return {
                "status": "error",
                "db": "unavailable",
                "version": version,
            }, 503

        return {"status": "ok", "db": "ok", "version": version}

    @app.get("/matches")
    def list_matches():
        with closing(get_connection()) as connection:
            with connection.cursor(as_dict=True) as cursor:
                cursor.execute("""
                    SELECT id, home_team, away_team, kickoff_at,
                           home_goals, away_goals, status
                    FROM dbo.matches
                    ORDER BY kickoff_at, id;
                """)
                matches = cursor.fetchall()

        try:
            balance_cents = fetch_bankroll_balance()
        except (OSError, ValueError, KeyError, TypeError):
            balance_cents = None

        return {
            "matches": matches,
            "balance_cents": balance_cents,
            "bankroll_status": "unavailable" if balance_cents is None else "ok",
        }

    @app.post("/matches")
    def add_match():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Send a JSON object."}, 400

        home_team = data.get("home_team")
        away_team = data.get("away_team")
        kickoff_at = data.get("kickoff_at")

        if not isinstance(home_team, str) or not isinstance(away_team, str):
            return {"error": "Enter both team names."}, 400

        home_team, away_team = home_team.strip(), away_team.strip()
        if not (1 <= len(home_team) <= 120 and 1 <= len(away_team) <= 120):
            return {"error": "Each team name must be 1 to 120 characters."}, 400
        if home_team.casefold() == away_team.casefold():
            return {"error": "Choose two different teams."}, 400

        try:
            kickoff = datetime.fromisoformat(kickoff_at)
            if kickoff.tzinfo is None:
                raise ValueError
            kickoff_utc = kickoff.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return {"error": "Send an ISO 8601 kickoff time with a timezone."}, 400

        try:
            with closing(get_connection()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO dbo.matches (home_team, away_team, kickoff_at, status)
                        OUTPUT INSERTED.id
                        VALUES (%s, %s, %s, 'scheduled');
                        """,
                        (home_team, away_team, kickoff_utc),
                    )
                    match_id = cursor.fetchone()[0]
                connection.commit()
        except Error:
            return {"error": "Journal database unavailable."}, 503

        return {"id": match_id}, 201

    return app
