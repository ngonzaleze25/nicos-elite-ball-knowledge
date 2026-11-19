import os
import time

from flask import Flask,g,request
from pymssql import Error

from services.bankroll.database import check_database_health, connect_with_retry
from services.bankroll.migrate import run_migrations


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

    return app