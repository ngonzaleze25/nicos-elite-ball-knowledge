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