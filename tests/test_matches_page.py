import pytest
from app import create_app
from journal.decisions import list_bet_decisions
from journal.matches import create_match, record_match_result, list_match_odds, list_matches
from journal.probability import estimate_from_results


def test_matches_page_adds_match_and_odds(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()
    client = app.test_client()

    page = client.get("/matches").get_data(as_text=True)
    assert "No matches match these filters." in page

    response = client.post(
        "/matches",
        data={
            "home_team": "Real Madrid",
            "away_team": "Barcelona",
            "kickoff_at": "2026-10-10T20:00:00",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Real Madrid vs Barcelona" in body
    assert "No odds entered yet." in body

    response = client.post(
        "/matches/1/odds",
        data={
            "bookmaker": "bet365",
            "home_odds": "2.10",
            "draw_odds": "3.40",
            "away_odds": "3.50",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "bet365:" in body
    assert "home 2.1" in body

    with app.app_context():
        assert len(list_matches()) == 1
        assert len(list_match_odds(1)) == 1


def test_matches_page_rejects_empty_match(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/matches",
        data={"home_team": "", "away_team": "Barcelona", "kickoff_at": "2026-10-03T20:00:00"},
    )
    assert response.status_code == 400
    assert "Home team cannot be empty." in response.get_data(as_text=True)


def test_home_page_links_to_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()
    client = app.test_client()

    page = client.get("/").get_data(as_text=True)
    assert 'href="/matches"' in page

def test_matches_page_converts_decimal_odds(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    response = app.test_client().get("/matches?decimal_odds=1.30")

    assert response.status_code == 200
    assert "76.92%" in response.get_data(as_text=True)


def test_matches_page_records_bet_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()
    client = app.test_client()

    client.post(
        "/deposits",
        data={"amount_euros": "100.00", "description": "Opening bankroll"},
    )
    client.post(
        "/matches",
        data={
            "home_team": "Real Madrid",
            "away_team": "Valencia",
            "kickoff_at": "2026-10-10T20:00",
        },
    )
    client.post(
        "/matches/1/odds",
        data={
            "bookmaker": "bet365",
            "home_odds": "2.50",
            "draw_odds": "3.40",
            "away_odds": "3.10",
        },
    )

    with app.app_context():
        for day in [1, 8, 15]:
            home_id = create_match("Real Madrid", "Sevilla", f"2026-09-{day:02d}T18:00:00Z")
            record_match_result(home_id, 2, 1)
            away_id = create_match("Betis", "Valencia", f"2026-09-{day:02d}T20:00:00Z")
            record_match_result(away_id, 1, 0)
        expected_probability = estimate_from_results(1)["probabilities"]["home"]

    response = client.post(
        "/matches/1/decisions",
        data={
            "bookmaker": "bet365",
            "selection": "home",
            "model_probability_percent": "0",  # Browser input must not override the model.
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "bet365 home:" in body
    assert f"model {expected_probability * 100:.2f}%" in body
    assert 'name="model_probability_percent"' not in body
    assert "implied 40.00%" in body
    assert "full Kelly €" in body
    assert "quarter Kelly €" in body
    assert "suggested stake €" in body
    assert "possible value" in body

    with app.app_context():
        decisions = list_bet_decisions(1)

    assert len(decisions) == 1
    assert decisions[0]["recommendation"] == "possible_value"

    assert decisions[0]["model_probability"] == pytest.approx(expected_probability)
