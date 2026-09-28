import pytest

from bankroll.kelly import (
    calculate_full_kelly_fraction,
    calculate_kelly_stake,
)


def test_calculates_full_and_quarter_kelly_stakes():
    bankroll = 1000
    decimal_odds = 2.20
    probability = 0.50

    full_fraction = calculate_full_kelly_fraction(
        decimal_odds,
        probability,
    )
    full_stake = calculate_kelly_stake(
        bankroll,
        decimal_odds,
        probability,
        multiplier=1.0,
    )
    quarter_stake = calculate_kelly_stake(
        bankroll,
        decimal_odds,
        probability,
        multiplier=0.25,
    )

    assert full_fraction == pytest.approx(0.083333, rel=1e-4)
    assert full_stake == pytest.approx(83.33, rel=1e-3)
    assert quarter_stake == pytest.approx(20.83, rel=1e-3)


def test_returns_zero_when_there_is_no_positive_edge():
    full_fraction = calculate_full_kelly_fraction(
        decimal_odds=2.0,
        probability=0.50,
    )
    quarter_stake = calculate_kelly_stake(
        bankroll=1000,
        decimal_odds=2.0,
        probability=0.50,
        multiplier=0.25,
    )

    assert full_fraction == 0
    assert quarter_stake == 0


@pytest.mark.parametrize("decimal_odds", [1.0, 0.5])
def test_rejects_invalid_decimal_odds(decimal_odds):
    with pytest.raises(ValueError):
        calculate_full_kelly_fraction(
            decimal_odds,
            probability=0.50,
        )


@pytest.mark.parametrize("probability", [-0.01, 1.01])
def test_rejects_invalid_probability(probability):
    with pytest.raises(ValueError):
        calculate_full_kelly_fraction(
            decimal_odds=2.0,
            probability=probability,
        )


def test_rejects_negative_bankroll():
    with pytest.raises(ValueError):
        calculate_kelly_stake(
            bankroll=-100,
            decimal_odds=2.0,
            probability=0.60,
        )


@pytest.mark.parametrize("multiplier", [0, -0.25, 1.01])
def test_rejects_invalid_multiplier(multiplier):
    with pytest.raises(ValueError):
        calculate_kelly_stake(
            bankroll=1000,
            decimal_odds=2.0,
            probability=0.60,
            multiplier=multiplier,
        )