from unittest.mock import Mock, call

import pymssql
import pytest

from services.bankroll import app as bankroll_app
from services.bankroll import database


def test_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL must be set"):
        database.get_connection()


@pytest.mark.parametrize("url", [
    "sqlite:///bankroll.db",
    "mssql://host/bankroll",
    "mssql://user@host/bankroll",
    "mssql://user:password@/bankroll",
    "mssql://user:password@host/",
])
def test_invalid_configuration_never_connects(monkeypatch, url):
    connect = Mock()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(database.pymssql, "connect", connect)
    with pytest.raises(ValueError):
        database.get_connection()
    connect.assert_not_called()


@pytest.mark.parametrize("port_text, expected_port", [("", 1433), (":1444", 1444)])
def test_connection_settings_and_encoded_credentials(monkeypatch, port_text, expected_port):
    monkeypatch.setenv(
        "DATABASE_URL",
        f"mssql://bank%40user:p%40ss%3Aword@localhost{port_text}/bankroll",
    )
    connect = Mock()
    monkeypatch.setattr(database.pymssql, "connect", connect)
    assert database.get_connection() is connect.return_value
    connect.assert_called_once_with(
        server="localhost", port=expected_port, user="bank@user",
        password="p@ss:word", database="bankroll", login_timeout=5,
        timeout=5, autocommit=False,
    )


def test_retry_recovers_and_does_not_log_credentials(monkeypatch, capsys):
    connection = object()
    connect = Mock(side_effect=[pymssql.OperationalError("private-password"), connection])
    sleep = Mock()
    monkeypatch.setattr(database, "get_connection", connect)
    monkeypatch.setattr(database.time, "sleep", sleep)
    assert database.connect_with_retry() is connection
    assert connect.call_count == 2
    sleep.assert_called_once_with(2)
    assert "private-password" not in capsys.readouterr().out


def test_retry_is_bounded_with_backoff(monkeypatch):
    connect = Mock(side_effect=pymssql.OperationalError("unavailable"))
    sleep = Mock()
    monkeypatch.setattr(database, "get_connection", connect)
    monkeypatch.setattr(database.time, "sleep", sleep)
    with pytest.raises(pymssql.OperationalError):
        database.connect_with_retry()
    assert connect.call_count == 6
    assert sleep.call_args_list == [call(2), call(4), call(8), call(16), call(32)]


def test_configuration_errors_are_not_retried(monkeypatch):
    connect = Mock(side_effect=ValueError("missing configuration"))
    sleep = Mock()
    monkeypatch.setattr(database, "get_connection", connect)
    monkeypatch.setattr(database.time, "sleep", sleep)
    with pytest.raises(ValueError):
        database.connect_with_retry()
    connect.assert_called_once_with()
    sleep.assert_not_called()


def test_startup_runs_migrations_then_closes_connection(monkeypatch):
    lifecycle = Mock()
    monkeypatch.setattr(bankroll_app, "connect_with_retry", lifecycle.connect)
    monkeypatch.setattr(bankroll_app, "run_migrations", lifecycle.migrate)
    app = bankroll_app.create_app()
    assert app.name == "services.bankroll.app"
    assert lifecycle.mock_calls == [
        call.connect(), call.migrate(lifecycle.connect.return_value),
        call.connect().close(),
    ]


def test_migration_failure_closes_connection_and_stops_startup(monkeypatch):
    connection = Mock()
    monkeypatch.setattr(bankroll_app, "connect_with_retry", Mock(return_value=connection))
    monkeypatch.setattr(bankroll_app, "run_migrations", Mock(side_effect=RuntimeError("migration failed")))
    with pytest.raises(RuntimeError, match="migration failed"):
        bankroll_app.create_app()
    connection.close.assert_called_once_with()


def test_connection_failure_does_not_run_migrations(monkeypatch):
    migrate = Mock()
    monkeypatch.setattr(bankroll_app, "connect_with_retry", Mock(side_effect=pymssql.OperationalError("unavailable")))
    monkeypatch.setattr(bankroll_app, "run_migrations", migrate)
    with pytest.raises(pymssql.OperationalError):
        bankroll_app.create_app()
    migrate.assert_not_called()
