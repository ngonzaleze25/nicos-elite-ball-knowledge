import pytest

from app import create_app
from journal.matches import (
    create_match,
    list_match_odds,
    list_matches,
    record_match_odds,
    record_match_result,
)


def test_create_and_list_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match(
            "Real Madrid",
            "Barcelona",
            "2026-10-03T20:00:00",
        )
        assert match_id == 1

        matches = list_matches()
        assert len(matches) == 1
        assert matches[0]["home_team"] == "Real Madrid"
        assert matches[0]["away_team"] == "Barcelona"
        assert matches[0]["status"] == "scheduled"
        assert matches[0]["home_goals"] is None


def test_record_and_list_match_odds(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match(
            "Sevilla",
            "Valencia",
            "2026-10-04T18:00:00",
        )
        record_match_odds(match_id, "bet365", 2.10, 3.40, 3.50)
        record_match_odds(match_id, "bwin", 2.05, 3.30, 3.60)

        odds = list_match_odds(match_id)
        assert len(odds) == 2
        assert odds[0]["bookmaker"] == "bet365"
        assert odds[0]["home_odds"] == 2.10
        assert odds[1]["bookmaker"] == "bwin"


def test_record_match_odds_can_update_same_bookmaker(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Athletic", "Betis", "2026-10-05T21:00:00")
        record_match_odds(match_id, "bet365", 1.90, 3.50, 4.00)
        record_match_odds(match_id, "bet365", 1.95, 3.40, 3.90)

        odds = list_match_odds(match_id)
        assert len(odds) == 1
        assert odds[0]["home_odds"] == 1.95


@pytest.mark.parametrize(
    "home, away, kickoff",
    [
        ("", "Barcelona", "2026-10-03T20:00:00"),
        ("Real Madrid", "  ", "2026-10-03T20:00:00"),
        ("Real Madrid", "Barcelona", ""),
    ],
)
def test_create_match_rejects_empty_fields(tmp_path, monkeypatch, home, away, kickoff):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        with pytest.raises(ValueError):
            create_match(home, away, kickoff)


def test_record_match_odds_rejects_invalid_bookmaker(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Osasuna", "Girona", "2026-10-06T17:00:00")
        with pytest.raises(ValueError):
            record_match_odds(match_id, "unibet", 2.0, 3.0, 3.5)


@pytest.mark.parametrize(
    "odds",
    [1.0, 0.5, -2, True, "2.1", float("inf"), float("-inf"), float("nan")],
)
def test_record_match_odds_rejects_invalid_prices(tmp_path, monkeypatch, odds):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Celta", "Mallorca", "2026-10-07T19:00:00")
        with pytest.raises(ValueError):
            record_match_odds(match_id, "bwin", odds, 3.2, 3.4)

def test_record_match_result_marks_match_finished(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Sevilla", "Valencia", "2026-10-04T18:00:00")
        record_match_result(match_id, 2, 1)

        match = list_matches()[0]
        assert match["home_goals"] == 2
        assert match["away_goals"] == 1
        assert match["status"] == "finished"