import math


def poisson_probability(expected_goals, goals):
    if expected_goals <= 0:
        raise ValueError("Expected goals must be greater than 0.")
    if goals < 0:
        raise ValueError("Goals cannot be negative.")

    return (
        math.exp(-expected_goals)
        * (expected_goals ** goals)
        / math.factorial(goals)
    )


def estimate_match_probabilities(
    home_expected_goals,
    away_expected_goals,
    max_goals=10,
):
    if home_expected_goals <= 0 or away_expected_goals <= 0:
        raise ValueError("Expected goals must be greater than 0.")

    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for home_goals in range(max_goals + 1):
        home_probability = poisson_probability(
            home_expected_goals,
            home_goals,
        )

        for away_goals in range(max_goals + 1):
            away_probability = poisson_probability(
                away_expected_goals,
                away_goals,
            )
            score_probability = home_probability * away_probability

            if home_goals > away_goals:
                home_win += score_probability
            elif home_goals == away_goals:
                draw += score_probability
            else:
                away_win += score_probability

    total = home_win + draw + away_win

    return {
        "home": home_win / total,
        "draw": draw / total,
        "away": away_win / total,
    }

def estimate_from_history(home_history, away_history):
    if len(home_history) < 3 or len(away_history) < 3:
        raise ValueError(
            "Need at least three earlier home games for the home team "
            "and three earlier away games for the away team."
        )

    home_expected = (
        sum(row["home_goals"] for row in home_history)
        / len(home_history)
        + sum(row["home_goals"] for row in away_history)
        / len(away_history)
    ) / 2

    away_expected = (
        sum(row["away_goals"] for row in away_history)
        / len(away_history)
        + sum(row["away_goals"] for row in home_history)
        / len(home_history)
    ) / 2

    # A small floor keeps the model usable after scoreless histories.
    home_expected = max(home_expected, 0.1)
    away_expected = max(away_expected, 0.1)

    return {
        "home_expected_goals": home_expected,
        "away_expected_goals": away_expected,
        "home_sample_size": len(home_history),
        "away_sample_size": len(away_history),
        "probabilities": estimate_match_probabilities(
            home_expected, away_expected
        ),
    }
