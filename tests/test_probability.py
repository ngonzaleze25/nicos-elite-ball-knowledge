import pytest

from journal.probability import (
    estimate_match_probabilities,
    poisson_probability,
)


def test_poisson_probability_for_exact_goal_count():
    probability = poisson_probability(expected_goals=1.5, goals=2)

    assert probability == pytest.approx(0.2510, rel=0.001)


def test_estimate_match_probabilities_returns_home_draw_and_away():
    probabilities = estimate_match_probabilities(
        home_expected_goals=1.6,
        away_expected_goals=1.1,
    )

    assert set(probabilities) == {"home", "draw", "away"}
    assert probabilities["home"] > probabilities["away"]
    assert sum(probabilities.values()) == pytest.approx(1.0, rel=0.01)


@pytest.mark.parametrize(
    "home_expected_goals, away_expected_goals",
    [
        (0, 1.2),
        (1.4, 0),
        (-1, 1.2),
        (1.4, -1),
    ],
)
def test_estimate_match_probabilities_rejects_invalid_expected_goals(
    home_expected_goals,
    away_expected_goals,
):
    with pytest.raises(ValueError):
        estimate_match_probabilities(
            home_expected_goals,
            away_expected_goals,
        )