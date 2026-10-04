from datetime import datetime, timezone

import pytest

from app import create_app
from bankroll.ledger import record_deposit
from database import get_db
from journal.bets import record_bet, settle_bet
from journal.decisions import record_bet_decision
from journal.matches import (
    create_match,
    list_visible_matches,
    record_match_odds,
    record_match_result,
)


NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)


@pytest.fixture
def workspace_app(tmp_path, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_STAKE_CENTS", "1000")
    monkeypatch.setattr("journal.matches.datetime", FixedDatetime)
    monkeypatch.setattr("journal.bets.datetime", FixedDatetime)
    app = create_app()
    with app.app_context():
        yield app


def test_upcoming_hides_past_distant_finished_and_postponed(workspace_app):
    create_match("Past", "Visitors", "2026-10-03T20:00")
    soon = create_match("Soon", "Visitors", "2026-10-05T20:00")
    distant = create_match("Distant", "Visitors", "2026-10-20T20:00")
    finished = create_match("Finished", "Visitors", "2026-10-06T20:00")
    record_match_result(finished, 1, 0)
    postponed = create_match("Postponed", "Visitors", "2026-10-07T20:00")
    db = get_db()
    db.execute(
        "INSERT INTO match_imports (external_id, match_id, api_status) VALUES (?, ?, ?)",
        (700, postponed, "POSTPONED"),
    )
    db.commit()

    assert [match["id"] for match in list_visible_matches()] == [soon]
    assert [match["id"] for match in list_visible_matches(days=30)] == [soon, distant]
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 5


def test_search_and_madrid_time(workspace_app):
    match_id = create_match("Real Madrid", "Valencia", "2026-10-05T20:00")
    create_match("Barcelona", "Sevilla", "2026-10-06T18:00")
    matches = list_visible_matches(search="  MADRID  ")

    assert [match["id"] for match in matches] == [match_id]
    assert matches[0]["kickoff_at"] == "2026-10-05T18:00:00+00:00"
    assert matches[0]["display_kickoff"].endswith("20:00")


def test_my_bets_keeps_past_open_bets_first(workspace_app):
    record_deposit(10000, "Opening bankroll")
    ids = []
    for home, kickoff in (("Awaiting", "2026-10-05T20:00"), ("Settled", "2026-10-06T20:00")):
        match_id = create_match(home, "Visitors", kickoff)
        record_match_odds(match_id, "bet365", 2.5, 3.4, 3.1)
        decision_id = record_bet_decision(match_id, "bet365", "home", 0.5)
        ids.append((match_id, record_bet(decision_id, 1000)))
    record_match_result(ids[1][0], 0, 1)
    settle_bet(ids[1][1])
    db = get_db()
    db.execute("UPDATE matches SET kickoff_at = ? WHERE id = ?", ("2026-10-02T18:00:00+00:00", ids[0][0]))
    db.commit()
    create_match("Unbet", "Visitors", "2026-10-07T20:00")

    matches = list_visible_matches("my_bets")
    assert [match["home_team"] for match in matches] == ["Awaiting", "Settled"]
    assert matches[0]["has_open_bet"]
    assert matches[0]["needs_manual_score"]
    html = workspace_app.test_client().get("/matches?view=my_bets").get_data(as_text=True)
    assert "Awaiting vs Visitors" in html
    assert "Unbet vs Visitors" not in html
    assert f'action="/matches/{ids[0][0]}/result"' in html


def test_history_is_newest_first_and_imported_results_are_read_only(workspace_app):
    old = create_match("Older", "Visitors", "2026-10-01T20:00")
    newer = create_match("Newer", "Visitors", "2026-10-03T20:00")
    record_match_result(old, 1, 0)
    record_match_result(newer, 2, 1)
    db = get_db()
    db.execute("INSERT INTO match_imports (external_id, match_id, api_status) VALUES (?, ?, ?)", (700, newer, "FINISHED"))
    db.commit()

    assert [match["id"] for match in list_visible_matches("history")] == [newer, old]
    html = workspace_app.test_client().get("/matches?view=history").get_data(as_text=True)
    assert "Newer vs Visitors" in html
    assert f'<details class="match" id="match-{newer}">' in html
    assert '<details class="match" open' not in html
    assert f'action="/matches/{newer}/result"' not in html


def test_saving_odds_preserves_view_search_and_window(workspace_app):
    match_id = create_match("Real Madrid", "Visitors", "2026-10-20T20:00")
    response = workspace_app.test_client().post(
        f"/matches/{match_id}/odds",
        data={"bookmaker": "bet365", "home_odds": "2.5", "draw_odds": "3.4", "away_odds": "3.1", "view": "upcoming", "search": "Madrid", "days": "30", "open_match": str(match_id)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Real Madrid vs Visitors" in html
    assert 'value="30" selected' in html
    assert 'name="search" type="search" value="Madrid"' in html
    assert "home 2.5" in html
    assert f'<details class="match" id="match-{match_id}" open>' in html
    assert response.history[0].headers["Location"].endswith(f"#match-{match_id}")


@pytest.mark.parametrize("kickoff", ["2005-10-25T14:00", "2026-06-30T23:59", "2027-07-01T00:00", "not-a-date", "2026-10-04"])
def test_manual_entries_reject_outside_season_or_invalid_dates(workspace_app, kickoff):
    response = workspace_app.test_client().post("/matches", data={"home_team": "Home", "away_team": "Away", "kickoff_at": kickoff})
    assert response.status_code == 400
    assert get_db().execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0


def test_legacy_outside_season_record_is_hidden_and_preserved(workspace_app):
    db = get_db()
    db.execute("INSERT INTO matches (home_team, away_team, kickoff_at, status) VALUES (?, ?, ?, ?)", ("Legacy", "Visitors", "2005-10-25T14:00", "finished"))
    db.commit()
    for view in ("upcoming", "my_bets", "history"):
        assert list_visible_matches(view) == []
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1


@pytest.mark.parametrize("query", ["view=unknown", "days=abc", "days=999"])
def test_invalid_filters_show_a_readable_error(workspace_app, query):
    response = workspace_app.test_client().get(f"/matches?{query}")
    assert response.status_code == 400
    assert 'role="alert"' in response.get_data(as_text=True)
