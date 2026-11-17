from flask import Flask

from services.bankroll.database import connect_with_retry
from services.bankroll.migrate import run_migrations


def create_app():
    app = Flask(__name__)

    connection = connect_with_retry()
    try:
        run_migrations(connection)
    finally:
        connection.close()

    return app