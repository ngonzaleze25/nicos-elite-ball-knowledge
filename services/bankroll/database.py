import os
import time
from urllib.parse import unquote, urlparse

import pymssql

def get_connection():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL must be set.")
    
    parsed = urlparse(database_url)

    if parsed.scheme != "mssql":
        raise ValueError("DATABASE_URL must use the mssql:// scheme.")
    
    if not all([
        parsed.hostname,
        parsed.username,
        parsed.password,
        parsed.path.lstrip("/"),
    ]):
        raise ValueError(
            "DATABASE_URL must include a host, username, password, and database."
        )
    tls_options = {"encryption": "require"} if parsed.hostname.endswith(".database.windows.net") else {}
    return pymssql.connect(
        server=parsed.hostname,
        port=parsed.port or 1433,
        user=unquote(parsed.username),
        password=unquote(parsed.password),
        database=unquote(parsed.path.lstrip("/")),
        login_timeout=5,
        timeout=5,
        autocommit=False,
        **tls_options,
    )


def connect_with_retry():
    for attempt in range(6):
        try:
            return get_connection()
        except pymssql.OperationalError:
            if attempt == 5:
                raise

            delay = 2 ** (attempt + 1)
            print(f"Database unavailable; retrying in {delay} seconds.")
            time.sleep(delay)

def check_database_health():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE dbo.health_probe "
                "SET checked_at = SYSUTCDATETIME() WHERE id = 1;"
            )
            cursor.execute("SELECT id FROM dbo.health_probe WHERE id = 1;")

            if cursor.fetchone() is None:
                raise RuntimeError("Health probe row 1 is missing.")
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()
