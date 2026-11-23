import os
import time
import json
from urllib.request import urlopen

from contextlib import closing
from flask import Flask,g,request
from pymssql import Error

from services.journal.betting import betting
from services.journal.database import check_database_health, connect_with_retry, get_connection
from services.journal.fixture_feed import FixtureFeedError, MissingFixtureToken, fetch_laliga_fixtures
from services.journal.migrate import run_migrations

def fetch_bankroll_balance():
    base_url = os.environ["BANKROLL_URL"].rstrip("/")
    with urlopen(f"{base_url}/balance", timeout=2) as response:
        return json.load(response)["balance_cents"]


def save_imported_fixtures(fixtures):
    if not fixtures:
        return
    with closing(get_connection()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                MERGE dbo.matches WITH (HOLDLOCK) AS existing
                USING OPENJSON(%s) WITH (
                    external_id BIGINT,
                    home_team NVARCHAR(120),
                    away_team NVARCHAR(120),
                    kickoff_at NVARCHAR(40),
                    source_status NVARCHAR(24),
                    status NVARCHAR(20),
                    home_goals INT,
                    away_goals INT
                ) AS fixture
                ON existing.external_id = fixture.external_id
                WHEN MATCHED THEN UPDATE SET
                    home_team = fixture.home_team, away_team = fixture.away_team,
                    kickoff_at = fixture.kickoff_at, source_status = fixture.source_status,
                    status = fixture.status, home_goals = fixture.home_goals,
                    away_goals = fixture.away_goals
                WHEN NOT MATCHED THEN INSERT (
                    external_id, home_team, away_team, kickoff_at, source_status,
                    status, home_goals, away_goals
                ) VALUES (
                    fixture.external_id, fixture.home_team, fixture.away_team,
                    fixture.kickoff_at, fixture.source_status, fixture.status,
                    fixture.home_goals, fixture.away_goals
                );
            """, (json.dumps(fixtures),))
        connection.commit()


def create_app():
    app = Flask(__name__)
    app.register_blueprint(betting)

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

    @app.after_request
    def add_cors_headers(response):
        ui_origin = os.environ.get("UI_ORIGIN", "http://127.0.0.1:8080")
        response.vary.add("Origin")
        if request.headers.get("Origin") == ui_origin:
            response.headers["Access-Control-Allow-Origin"] = ui_origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
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
        try:
            with closing(get_connection()) as connection:
                with connection.cursor(as_dict=True) as cursor:
                    cursor.execute("""
                        SELECT id, home_team, away_team, kickoff_at,
                               home_goals, away_goals, status, source_status
                        FROM dbo.matches
                        WHERE external_id IS NOT NULL
                        ORDER BY CASE WHEN kickoff_at IS NULL THEN 1 ELSE 0 END, kickoff_at, id;
                    """)
                    matches = cursor.fetchall()
        except Error:
            return {"error": "Journal database unavailable. Try again shortly."}, 503

        try:
            balance_cents = fetch_bankroll_balance()
        except (OSError, ValueError, KeyError, TypeError):
            balance_cents = None

        return {
            "matches": matches,
            "balance_cents": balance_cents,
            "bankroll_status": "unavailable" if balance_cents is None else "ok",
        }

    @app.post("/matches/sync")
    def sync_matches():
        try:
            fixtures = fetch_laliga_fixtures()
            save_imported_fixtures(fixtures)
        except MissingFixtureToken as error:
            return {"error": str(error)}, 503
        except FixtureFeedError as error:
            return {"error": str(error)}, 502
        except Error:
            return {"error": "Journal database unavailable. Try again shortly."}, 503

        return {"synced": len(fixtures)}

    return app
