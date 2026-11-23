import os
import time
from contextlib import closing

from flask import Flask,g,request
from pymssql import Error

from services.bankroll.database import (
    check_database_health,
    connect_with_retry,
    get_connection,
)
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

    @app.get("/balance")
    def balance():
        try:
            with closing(get_connection()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT COALESCE(SUM(CAST(amount_cents AS BIGINT)), 0)
                        FROM dbo.bankroll_transactions;
                    """)
                    balance_cents = cursor.fetchone()[0]
        except Error:
            return {"error": "Bankroll database unavailable"}, 503

        return {"balance_cents": balance_cents}

    @app.post("/deposits")
    def add_deposit():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return {"error": "Send a JSON object."}, 400

        amount_cents = data.get("amount_cents")
        description = data.get("description")

        if type(amount_cents) is not int or not 1 <= amount_cents <= 2_147_483_647:
            return {"error": "amount_cents must be a positive SQL Server integer."}, 400

        if not isinstance(description, str) or not description.strip():
            return {"error": "Enter a description."}, 400

        try:
            with closing(get_connection()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO dbo.bankroll_transactions
                            (transaction_type, amount_cents, description)
                        OUTPUT INSERTED.id
                        VALUES ('deposit', %s, %s);
                        """,
                        (amount_cents, description.strip()),
                    )
                    deposit_id = cursor.fetchone()[0]
                connection.commit()
        except Error:
            return {"error": "Bankroll database unavailable"}, 503

        return {"id": deposit_id, "amount_cents": amount_cents}, 201

    return app
