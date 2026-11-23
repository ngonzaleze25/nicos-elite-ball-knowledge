import io
import json
from unittest.mock import MagicMock, Mock

import pymssql
import pytest

from services.bankroll import app as bankroll
from services.bankroll import database as bankroll_database
from services.journal import app as journal
from services.journal import database as journal_database


@pytest.fixture
def clients(monkeypatch):
    def make(module):
        monkeypatch.setattr(module, "connect_with_retry", Mock())
        monkeypatch.setattr(module, "run_migrations", Mock())
        connection = MagicMock()
        monkeypatch.setattr(module, "get_connection", Mock(return_value=connection))
        cursor = connection.cursor.return_value.__enter__.return_value
        return module.create_app().test_client(), connection, cursor

    return make


def test_deposit_validation_requires_positive_integer_cents_and_description(clients):
    client, connection, _ = clients(bankroll)
    invalid_bodies = [[], {"amount_cents": True}, {"amount_cents": 1, "description": "  "}]
    for body in invalid_bodies:
        assert client.post("/deposits", json=body).status_code == 400
    connection.commit.assert_not_called()


def test_deposit_commits_and_balance_reads_the_ledger(clients):
    client, connection, cursor = clients(bankroll)
    cursor.fetchone.side_effect = [(17,), (1250,)]
    result = client.post("/deposits", json={"amount_cents": 1250, "description": " Test "})
    assert result.status_code == 201
    assert result.json == {"id": 17, "amount_cents": 1250}
    connection.commit.assert_called_once()
    assert client.get("/balance").json == {"balance_cents": 1250}


@pytest.mark.parametrize("module,path", [(bankroll, "/balance"), (journal, "/matches")])
def test_database_outage_returns_json_503(clients, module, path):
    client, _, _ = clients(module)
    module.get_connection.side_effect = pymssql.OperationalError("database connection failed")
    response = client.get(path)
    assert response.status_code == 503
    assert response.json["error"]


def test_journal_shows_saved_matches_when_bankroll_times_out(clients, monkeypatch):
    client, _, cursor = clients(journal)
    cursor.fetchall.return_value = [{"id": 1, "home_team": "Celta", "away_team": "Mallorca"}]
    monkeypatch.setenv("BANKROLL_URL", "http://bankroll:8000/")
    fetch = Mock(side_effect=[io.BytesIO(b'{"balance_cents":1250}'), TimeoutError()])
    monkeypatch.setattr(journal, "urlopen", fetch)

    healthy = client.get("/matches")
    assert healthy.json["balance_cents"] == 1250 and healthy.json["bankroll_status"] == "ok"
    fetch.assert_called_with("http://bankroll:8000/balance", timeout=2)

    degraded = client.get("/matches")
    assert degraded.status_code == 200
    assert degraded.json["matches"] == healthy.json["matches"]
    assert degraded.json["balance_cents"] is None
    assert degraded.json["bankroll_status"] == "unavailable"


def test_journal_import_writes_provider_records_and_commits(clients, monkeypatch):
    client, connection, cursor = clients(journal)
    fixtures = [{"external_id": 17, "home_team": "Celta", "away_team": "Mallorca"}]
    monkeypatch.setattr(journal, "fetch_laliga_fixtures", Mock(return_value=fixtures))
    result = client.post("/matches/sync")
    assert result.status_code == 200 and result.json == {"synced": 1}
    assert json.loads(cursor.execute.call_args.args[1][0]) == fixtures
    connection.commit.assert_called_once()


def test_journal_health_probe_rolls_back_and_reports_missing_table_row(clients, monkeypatch):
    client, connection, cursor = clients(journal)
    monkeypatch.setattr(journal_database, "get_connection", Mock(return_value=connection))
    cursor.fetchone.side_effect = [(1,), None]

    healthy = client.get("/health")
    assert healthy.status_code == 200 and healthy.json["db"] == "ok"
    unavailable = client.get("/health")
    assert unavailable.status_code == 503 and unavailable.json["db"] == "unavailable"
    assert connection.rollback.call_count == 2
    connection.commit.assert_not_called()


def test_journal_decodes_database_credentials_and_targets_its_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mssql://journal_app:sample%40password@sqlserver:1433/journal")
    connect = Mock()
    monkeypatch.setattr(journal_database.pymssql, "connect", connect)
    assert journal_database.get_connection() is connect.return_value
    settings = connect.call_args.kwargs
    assert settings["user"] == "journal_app"
    assert settings["password"] == "sample@password"
    assert settings["database"] == "journal"
    assert settings["autocommit"] is False


@pytest.mark.parametrize("database", [bankroll_database, journal_database])
def test_azure_sql_requires_encrypted_connections(database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mssql://sample:pass@example.database.windows.net/db")
    connect = Mock()
    monkeypatch.setattr(database.pymssql, "connect", connect)
    database.get_connection()
    assert connect.call_args.kwargs["encryption"] == "require"


@pytest.mark.parametrize("module", [bankroll, journal])
def test_cors_permits_only_the_configured_browser_origin(clients, module, monkeypatch):
    client, _, _ = clients(module)
    monkeypatch.setenv("UI_ORIGIN", "https://ui.example")
    allowed = client.options("/health", headers={"Origin": "https://ui.example"})
    blocked = client.options("/health", headers={"Origin": "https://other.example"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://ui.example"
    assert "Access-Control-Allow-Origin" not in blocked.headers
    assert "Origin" in allowed.vary and "Origin" in blocked.vary
