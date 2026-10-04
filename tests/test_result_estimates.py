import pytest

from app import create_app
from journal.matches import create_match, record_match_result
from journal.probability import estimate_from_results


@pytest.fixture
def history(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        for day in [1, 8, 15]:
            home_id = create_match(
                "Barcelona", "Sevilla",
                f"2026-09-{day:02d}T18:00:00Z",
            )
            record_match_result(home_id, 2, 1)

            away_id = create_match(
                "Valencia", "Real Madrid",
                f"2026-09-{day:02d}T20:00:00Z",
            )
            record_match_result(away_id, 1, 3)

        target_id = create_match(
            "Barcelona", "Real Madrid",
            "2026-10-10T18:00:00Z",
        )
        yield target_id


def test_estimates_use_saved_scores(history):
    estimate = estimate_from_results(history)

    assert estimate["home_expected_goals"] == pytest.approx(1.5)
    assert estimate["away_expected_goals"] == pytest.approx(2.0)
    assert estimate["home_sample_size"] == 3
    assert estimate["away_sample_size"] == 3

    probabilities = estimate["probabilities"]
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert probabilities["away"] > probabilities["home"]


def test_target_and_future_results_do_not_change_estimate(history):
    before = estimate_from_results(history)

    record_match_result(history, 9, 0)
    future_id = create_match(
        "Barcelona", "Real Madrid",
        "2026-10-20T18:00:00Z",
    )
    record_match_result(future_id, 9, 0)

    assert estimate_from_results(history) == before


def test_insufficient_history_has_clear_error(history):
    other_id = create_match(
        "Betis", "Mallorca",
        "2026-10-10T20:00:00Z",
    )

    with pytest.raises(ValueError, match="at least three"):
        estimate_from_results(other_id)


def test_missing_match_is_rejected(history):
    with pytest.raises(ValueError, match="does not exist"):
        estimate_from_results(999999)


def test_scoreless_history_still_produces_probabilities(history):
    from database import get_db

    db = get_db()
    db.execute(
        "UPDATE matches SET home_goals = 0, away_goals = 0 "
        "WHERE status = 'finished'"
    )
    db.commit()

    estimate = estimate_from_results(history)

    assert estimate["home_expected_goals"] == pytest.approx(0.1)
    assert estimate["away_expected_goals"] == pytest.approx(0.1)
    assert sum(estimate["probabilities"].values()) == pytest.approx(1.0)

@pytest.mark.parametrize("selection", ["home", "draw", "away"])
def test_decision_route_saves_selected_model_probability(history, selection):
    from flask import current_app
    from journal.matches import record_match_odds
    from journal.decisions import list_bet_decisions

    record_match_odds(history, "bet365", 2.5, 3.4, 3.1)
    expected = estimate_from_results(history)["probabilities"][selection]
    response = current_app.test_client().post(
        f"/matches/{history}/decisions",
        data={"bookmaker": "bet365", "selection": selection,
              "model_probability_percent": "99", "view": "upcoming",
              "open_match": str(history)},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"#match-{history}")
    page = current_app.test_client().get(response.headers["Location"]).get_data(as_text=True)
    assert f'<details class="match" id="match-{history}" open>' in page
    decision = list_bet_decisions(history)[0]
    assert decision["selection"] == selection
    assert decision["model_probability"] == pytest.approx(expected)


def test_decision_without_history_is_not_saved(history):
    from flask import current_app
    from journal.matches import record_match_odds
    from journal.decisions import list_bet_decisions

    target = create_match("Betis", "Mallorca", "2026-10-10T20:00:00Z")
    record_match_odds(target, "bet365", 2.5, 3.4, 3.1)
    client = current_app.test_client()
    page = client.get("/matches").get_data(as_text=True)
    assert f'action="/matches/{target}/decisions"' not in page
    response = client.post(
        f"/matches/{target}/decisions",
        data={"bookmaker": "bet365", "selection": "home"},
    )
    assert response.status_code == 400
    assert "at least three" in response.get_data(as_text=True)
    assert list_bet_decisions(target) == []
