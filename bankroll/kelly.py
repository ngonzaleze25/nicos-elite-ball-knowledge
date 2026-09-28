def calculate_full_kelly_fraction(decimal_odds, probability):
    if decimal_odds <= 1:
        raise ValueError("Decimal odds must be greater than 1.")

    if probability < 0 or probability > 1:
        raise ValueError("Probability must be between 0 and 1.")

    net_odds = decimal_odds - 1
    loss_probability = 1 - probability

    kelly_fraction = (
        (net_odds * probability) - loss_probability
    ) / net_odds

    return max(0.0, kelly_fraction)


def calculate_kelly_stake(
    bankroll,
    decimal_odds,
    probability,
    multiplier=1.0,
):
    if bankroll < 0:
        raise ValueError("Bankroll cannot be negative.")

    if multiplier <= 0 or multiplier > 1:
        raise ValueError("Multiplier must be greater than 0 and at most 1.")

    full_fraction = calculate_full_kelly_fraction(
        decimal_odds,
        probability,
    )

    return bankroll * full_fraction * multiplier