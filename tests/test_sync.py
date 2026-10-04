import pytest

from copy import deepcopy

from app import create_app
from database import get_db
from journal.matches import record_match_odds
from journal.sync import import_api_matches, normalise_api_match
from datetime import datetime, timedelta, timezone

from bankroll.ledger import get_balance_cents, record_deposit
from journal.bets import record_bet
from journal.decisions import record_bet_decision

@pytest.fixture
def api_fixture():
    return {
        "id": 700,
        "competition": {"code": "PD"},
        "season": {"startDate": "2026-08-15"},
        "homeTeam": {"name": "Sevilla FC"},
        "awayTeam": {"name": "Valencia CF"},
        "utcDate": "2026-08-15T19:30:00Z",
        "status": "FINISHED",
        "score": {"fullTime": {"home": 2, "away": 1}},
    }


def test_normalise_finished_fixture(api_fixture):
    match = normalise_api_match(api_fixture)

    assert match["external_id"] == 700
    assert match["home_team"] == "Sevilla FC"
    assert match["away_team"] == "Valencia CF"
    assert match["kickoff_at"] == "2026-08-15T19:30:00+00:00"
    assert match["status"] == "finished"
    assert match["api_status"] == "FINISHED"
    assert match["home_goals"] == 2
    assert match["away_goals"] == 1


@pytest.mark.parametrize(
    "api_status",
    ["TIMED", "IN_PLAY", "POSTPONED", "CANCELLED"],
)
def test_nonfinal_fixture_does_not_store_final_score(api_fixture, api_status):
    api_fixture["status"] = api_status

    match = normalise_api_match(api_fixture)

    assert match["status"] == "scheduled"
    assert match["api_status"] == api_status
    assert match["home_goals"] is None
    assert match["away_goals"] is None


def test_incomplete_fixture_is_rejected():
    with pytest.raises(ValueError, match="incomplete"):
        normalise_api_match({"id": 700})

@pytest.fixture
def sync_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        yield app


def test_import_saves_fixture_and_api_link(sync_app, api_fixture):
    result = import_api_matches([api_fixture])
    db = get_db()

    assert result == {"created": 1, "updated": 0}
    match = db.execute("SELECT * FROM matches").fetchone()
    link = db.execute("SELECT * FROM match_imports").fetchone()

    assert match["home_team"] == "Sevilla FC"
    assert match["status"] == "finished"
    assert match["home_goals"] == 2
    assert match["away_goals"] == 1
    assert link["external_id"] == 700
    assert link["match_id"] == match["id"]
    assert link["api_status"] == "FINISHED"


def test_repeated_import_updates_without_losing_odds(sync_app, api_fixture):
    import_api_matches([api_fixture])
    db = get_db()
    match_id = db.execute("SELECT id FROM matches").fetchone()["id"]
    record_match_odds(match_id, "bet365", 2.5, 3.4, 3.1)

    api_fixture["score"]["fullTime"]["away"] = 2
    result = import_api_matches([api_fixture])

    assert result == {"created": 0, "updated": 1}
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM match_imports").fetchone()[0] == 1
    match = db.execute("SELECT * FROM matches").fetchone()
    odds = db.execute("SELECT * FROM match_odds").fetchone()

    assert match["id"] == match_id
    assert match["away_goals"] == 2
    assert odds["match_id"] == match_id
    assert odds["home_odds"] == 2.5


def test_invalid_batch_saves_nothing(sync_app, api_fixture):
    invalid = deepcopy(api_fixture)
    invalid["id"] = 701
    invalid["homeTeam"] = {}

    with pytest.raises(ValueError, match="incomplete"):
        import_api_matches([api_fixture, invalid])

    db = get_db()
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM match_imports").fetchone()[0] == 0


@pytest.mark.parametrize(
    "api_status, days_until_kickoff, allowed",
    [
        ("TIMED", 1, True),
        ("SCHEDULED", 1, True),
        ("TIMED", -1, False),
        ("IN_PLAY", 1, False),
        ("PAUSED", 1, False),
        ("POSTPONED", 1, False),
        ("CANCELLED", 1, False),
    ],
)
def test_imported_fixture_controls_stake_availability(
    sync_app, api_fixture, api_status, days_until_kickoff, allowed
):
    sync_app.config["MAX_STAKE_CENTS"] = 1000
    kickoff = datetime.now(timezone.utc) + timedelta(days=days_until_kickoff)
    api_fixture["utcDate"] = kickoff.isoformat()
    api_fixture["status"] = api_status
    import_api_matches([api_fixture])

    db = get_db()
    match_id = db.execute("SELECT id FROM matches").fetchone()["id"]
    record_deposit(10000, "Opening bankroll")
    record_match_odds(match_id, "bet365", 2.5, 3.4, 3.1)
    decision_id = record_bet_decision(
        match_id, "bet365", "home", 0.5
    )

    response = sync_app.test_client().get("/matches")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert ("Sevilla FC vs Valencia CF" in html) == allowed
    if allowed:
        assert f"Status: {api_status}" in html
    assert (f'action="/decisions/{decision_id}/bets"' in html) == allowed

    if allowed:
        record_bet(decision_id, 1000)
        assert get_balance_cents() == 9000
        assert db.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1
    else:
        with pytest.raises(ValueError, match="Cannot record"):
            record_bet(decision_id, 1000)

        assert get_balance_cents() == 10000
        assert db.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0

def test_user_triggered_sync_imports_without_duplicates(
    sync_app, api_fixture, monkeypatch
):
    monkeypatch.setattr(
        "journal.sync.fetch_laliga_matches",
        lambda: [api_fixture],
    )
    client = sync_app.test_client()
    db = get_db()

    assert client.get("/matches").status_code == 200
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0

    response = client.post("/matches/sync")
    assert response.status_code == 200
    assert "Sevilla FC vs Valencia CF" not in response.get_data(as_text=True)
    assert "Sevilla FC vs Valencia CF" in client.get("/matches?view=history").get_data(as_text=True)
    assert "Sync complete: 1 fixtures added, 0 existing fixtures updated." in response.get_data(as_text=True)

    response = client.post("/matches/sync")
    assert response.status_code == 200
    assert "Sync complete: 0 fixtures added, 1 existing fixtures updated." in response.get_data(as_text=True)
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM match_imports").fetchone()[0] == 1


def test_sync_failure_preserves_data_and_manual_tracking(
    sync_app, api_fixture, monkeypatch
):
    import_api_matches([api_fixture])
    record_deposit(10000, "Opening bankroll")

    def unavailable_api():
        raise ValueError("API unavailable")

    monkeypatch.setattr(
        "journal.sync.fetch_laliga_matches",
        unavailable_api,
    )
    client = sync_app.test_client()

    response = client.post("/matches/sync")
    assert response.status_code == 503
    assert "API unavailable" in response.get_data(as_text=True)
    assert get_balance_cents() == 10000

    response = client.post(
        "/matches",
        data={
            "home_team": "Betis",
            "away_team": "Getafe",
            "kickoff_at": "2026-10-10T18:00",
        },
    )
    assert response.status_code == 302

    db = get_db()
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM match_imports").fetchone()[0] == 1
