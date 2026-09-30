import pytest

from journal.odds import implied_probability


def test_converts_decimal_odds_to_percentage():
    assert implied_probability(1.30) == pytest.approx(76.9230769)
    assert implied_probability(2.00) == 50.0


def test_rejects_odds_of_one():
    with pytest.raises(ValueError):
        implied_probability(1.0)