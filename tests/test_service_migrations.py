from unittest.mock import Mock, call

import pytest

from services.bankroll import migrate as bankroll_migrations
from services.journal import migrate as journal_migrations


@pytest.mark.parametrize("runner", [bankroll_migrations, journal_migrations])
def test_migrations_apply_in_order_and_are_skipped_when_recorded(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "__file__", str(tmp_path / "migrate.py"))
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (migration_dir / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    database = Mock()
    cursor = database.cursor.return_value
    cursor.fetchall.side_effect = [[], [("001_first.sql",), ("002_second.sql",)]]

    runner.run_migrations(database)
    runner.run_migrations(database)

    statements = cursor.execute.call_args_list
    assert [statement for statement in statements if statement in (call("SELECT 1;"), call("SELECT 2;"))] == [
        call("SELECT 1;"), call("SELECT 2;")
    ]
    recorded = [
        statement.args[1][0] for statement in statements
        if statement.args[0].startswith("INSERT INTO dbo.schema_migrations")
    ]
    assert recorded == ["001_first.sql", "002_second.sql"]
    database.rollback.assert_not_called()


@pytest.mark.parametrize("runner", [bankroll_migrations, journal_migrations])
def test_failed_migration_is_rolled_back_and_leaves_no_record(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "__file__", str(tmp_path / "migrate.py"))
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_bad.sql").write_text("INVALID SQL;", encoding="utf-8")
    database = Mock()
    cursor = database.cursor.return_value
    cursor.fetchall.return_value = []

    def execute(sql, *args):
        if sql == "INVALID SQL;":
            raise RuntimeError("test migration failed")

    cursor.execute.side_effect = execute
    with pytest.raises(RuntimeError, match="test migration failed"):
        runner.run_migrations(database)

    database.rollback.assert_called_once()
    cursor.close.assert_called_once()
    assert all(
        not statement.args[0].startswith("INSERT INTO dbo.schema_migrations")
        for statement in cursor.execute.call_args_list
    )
