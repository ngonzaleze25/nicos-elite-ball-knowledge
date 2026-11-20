import os
import time

from contextlib import closing
from flask import Flask,g,request
from pymssql import Error

from services.journal.database import check_database_health, connect_with_retry, get_connection
from services.journal.migrate import run_migrations


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

        return {"matches": matches}

    return app
