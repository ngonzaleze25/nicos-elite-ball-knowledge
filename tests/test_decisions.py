import pytest

from app import create_app
from bankroll.ledger import record_deposit
from journal.decisions import list_bet_decisions, record_bet_decision
from journal.matches import create_match, record_match_odds


def test_record_bet_decision_marks_possible_value(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Real Madrid", "Valencia", "2026-10-10T20:00")
        record_match_odds(match_id, "bet365", 2.50, 3.40, 3.10)

        decision_id = record_bet_decision(
            match_id=match_id,
            bookmaker="bet365",
            selection="home",
            model_probability=0.50,
        )

        decisions = list_bet_decisions(match_id)

        assert decision_id == 1
        assert len(decisions) == 1
        assert decisions[0]["selection"] == "home"
        assert decisions[0]["decimal_odds"] == 2.50
        assert decisions[0]["implied_probability"] == pytest.approx(0.40)
        assert decisions[0]["value_margin"] == pytest.approx(0.10)
        assert decisions[0]["recommendation"] == "possible_value"


def test_record_bet_decision_marks_no_value(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Sevilla", "Betis", "2026-10-11T18:00")
        record_match_odds(match_id, "bwin", 1.80, 3.50, 4.20)

        record_bet_decision(
            match_id=match_id,
            bookmaker="bwin",
            selection="home",
            model_probability=0.45,
        )

        decision = list_bet_decisions(match_id)[0]

        assert decision["implied_probability"] == pytest.approx(1 / 1.80)
        assert decision["value_margin"] == pytest.approx(0.45 - (1 / 1.80))
        assert decision["recommendation"] == "no_value"


@pytest.mark.parametrize("selection", ["home", "draw", "away"])
def test_record_bet_decision_uses_selected_odds(selection, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Atletico", "Villarreal", "2026-10-12T21:00")
        record_match_odds(match_id, "bet365", 2.00, 3.25, 4.00)

        record_bet_decision(
            match_id=match_id,
            bookmaker="bet365",
            selection=selection,
            model_probability=0.40,
        )

        decision = list_bet_decisions(match_id)[0]

        expected_odds = {
            "home": 2.00,
            "draw": 3.25,
            "away": 4.00,
        }[selection]

        assert decision["decimal_odds"] == expected_odds


def test_record_bet_decision_rejects_missing_odds(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Osasuna", "Girona", "2026-10-13T17:00")

        with pytest.raises(ValueError):
            record_bet_decision(
                match_id=match_id,
                bookmaker="bet365",
                selection="home",
                model_probability=0.50,
            )


def test_record_bet_decision_caps_quarter_kelly_by_stake_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        record_deposit(10000, "Opening bankroll")
        match_id = create_match("Real Madrid", "Valencia", "2026-10-10T20:00")
        record_match_odds(match_id, "bet365", 2.50, 3.40, 3.10)

        record_bet_decision(
            match_id=match_id,
            bookmaker="bet365",
            selection="home",
            model_probability=0.50,
            max_stake_cents=1000,
        )

        decision = list_bet_decisions(match_id)[0]

        assert decision["full_kelly_stake_cents"] == 1667
        assert decision["quarter_kelly_stake_cents"] == 417
        assert decision["recommended_stake_cents"] == 417


def test_record_bet_decision_never_recommends_more_than_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        record_deposit(10000, "Opening bankroll")
        match_id = create_match("Atletico", "Villarreal", "2026-10-12T21:00")
        record_match_odds(match_id, "bet365", 5.00, 3.25, 1.80)

        record_bet_decision(
            match_id=match_id,
            bookmaker="bet365",
            selection="home",
            model_probability=0.60,
            max_stake_cents=1000,
        )

        decision = list_bet_decisions(match_id)[0]

        assert decision["quarter_kelly_stake_cents"] > 1000
        assert decision["recommended_stake_cents"] == 1000

@pytest.mark.parametrize(
    "probability",
    [-0.1, 1.1, True, "0.5", float("inf"), float("-inf"), float("nan")],
)
def test_decision_rejects_invalid_probability(tmp_path, monkeypatch, probability):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        match_id = create_match("Sevilla", "Valencia", "2026-10-10T20:00")
        record_match_odds(match_id, "bet365", 2.5, 3.4, 3.1)

        with pytest.raises(ValueError):
            record_bet_decision(
                match_id=match_id,
                bookmaker="bet365",
                selection="home",
                model_probability=probability,
            )

        assert list_bet_decisions(match_id) == []