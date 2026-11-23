import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from services.journal import app as journal_app
from services.journal import fixture_feed


def provider_fixture(status="TIMED", utc_date="2026-11-27T20:00:00Z"):
    return {
        "id": 1234,
        "homeTeam": {"name": "Celta"},
        "awayTeam": {"name": "Mallorca"},
        "competition": {"code": "PD"},
        "season": {"startDate": "2026-08-15"},
        "utcDate": utc_date,
        "status": status,
    }


def test_fetches_provider_teams_and_times(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "sample-token")
    item = provider_fixture()
    pending = dict(provider_fixture("SCHEDULED", None), id=1235)
    request = Mock(return_value=io.BytesIO(json.dumps({"matches": [item, pending]}).encode()))
    monkeypatch.setattr(fixture_feed, "urlopen", request)

    timed, unscheduled = fixture_feed.fetch_laliga_fixtures()

    assert timed["home_team"] == "Celta"
    assert timed["kickoff_at"] == "2026-11-27T20:00:00+00:00"
    assert timed["source_status"] == "TIMED"
    assert unscheduled["kickoff_at"] is None
    assert unscheduled["source_status"] == "SCHEDULED"
    outgoing = request.call_args.args[0]
    assert outgoing.full_url.endswith("/competitions/PD/matches?season=2026")
    assert outgoing.get_header("X-auth-token") == "sample-token"


def test_feed_rejects_duplicate_ids_before_import(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "sample-token")
    item = provider_fixture()
    body = io.BytesIO(json.dumps({"matches": [item, item]}).encode())
    monkeypatch.setattr(fixture_feed, "urlopen", Mock(return_value=body))

    with pytest.raises(fixture_feed.FixtureFeedError, match="duplicate"):
        fixture_feed.fetch_laliga_fixtures()


@pytest.fixture
def journal_client(monkeypatch):
    monkeypatch.setattr(journal_app, "connect_with_retry", Mock())
    monkeypatch.setattr(journal_app, "run_migrations", Mock())
    return journal_app.create_app().test_client()


def test_sync_uses_feed_instead_of_submitted_teams(monkeypatch, journal_client):
    fixtures = [{"external_id": 1234, "home_team": "Celta", "away_team": "Mallorca"}]
    monkeypatch.setattr(journal_app, "fetch_laliga_fixtures", Mock(return_value=fixtures))
    save = Mock()
    monkeypatch.setattr(journal_app, "save_imported_fixtures", save)

    invented = {"home_team": "Invented", "away_team": "Made up"}
    assert journal_client.post("/matches", json=invented).status_code == 405
    response = journal_client.post("/matches/sync", json=invented)
    assert response.status_code == 200
    assert response.json == {"synced": 1}
    save.assert_called_once_with(fixtures)


def test_missing_token_does_not_write_fixtures(monkeypatch, journal_client):
    monkeypatch.delenv("FOOTBALL_DATA_API_TOKEN", raising=False)
    save = Mock()
    monkeypatch.setattr(journal_app, "save_imported_fixtures", save)

    response = journal_client.post("/matches/sync")
    assert response.status_code == 503
    assert "token has not been configured" in response.json["error"]
    save.assert_not_called()


def test_invalid_token_error_identifies_the_credential(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "sample-token")
    body = io.BytesIO(b'{"message": "Your API token is invalid."}')
    error = HTTPError(fixture_feed.MATCHES_URL, 400, "Bad Request", {}, body)
    monkeypatch.setattr(fixture_feed, "urlopen", Mock(side_effect=error))

    with pytest.raises(fixture_feed.FixtureFeedError, match="rejected the token"):
        fixture_feed.fetch_laliga_fixtures()
