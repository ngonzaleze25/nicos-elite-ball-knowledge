from pathlib import Path


def ensure_migration_table(cursor):
    cursor.execute("""
        IF OBJECT_ID(N'dbo.schema_migrations', N'U') IS NULL
            CREATE TABLE dbo.schema_migrations (
                filename NVARCHAR(255) NOT NULL PRIMARY KEY
            );
    """)

def get_applied_migrations(cursor):
    cursor.execute("SELECT filename FROM dbo.schema_migrations;")
    rows = cursor.fetchall()
    return {row[0] for row in rows}

def apply_migration(cursor, migration_path):
    sql = migration_path.read_text(encoding="utf-8")
    cursor.execute(sql)
    cursor.execute(
        "INSERT INTO dbo.schema_migrations (filename) VALUES (%s);",
        (migration_path.name,),
    )

def run_migrations(connection):
    migration_dir = Path(__file__).parent / "migrations"
    cursor = connection.cursor()

    try:
        ensure_migration_table(cursor)
        applied = get_applied_migrations(cursor)
        connection.commit()

        for path in sorted(migration_dir.glob("*.sql")):
            if path.name in applied:
                continue

            apply_migration(cursor, path)
            connection.commit()
            print(f"Applied migration: {path.name}")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()