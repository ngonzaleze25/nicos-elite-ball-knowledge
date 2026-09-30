import math


def implied_probability(decimal_odds: float) -> float:
    """Return implied probability as a percentage."""
    if not math.isfinite(decimal_odds) or decimal_odds <= 1:
        raise ValueError("Decimal odds must be greater than 1.")

    return (1 / decimal_odds) * 100