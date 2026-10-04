import pytest

from app import create_app
from bankroll.ledger import get_balance_cents, record_deposit, validate_stake
from database import get_db


def test_deposits_build_a_persistent_balance(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        assert get_balance_cents() == 0
        record_deposit(1050, "Opening deposit")
        record_deposit(450, "Top up")
        assert get_balance_cents() == 1500

        rows = get_db().execute(
            "SELECT transaction_type, amount_cents, description "
            "FROM bankroll_transactions ORDER BY id"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("deposit", 1050, "Opening deposit"),
            ("deposit", 450, "Top up"),
        ]

    with create_app().app_context():
        assert get_balance_cents() == 1500


@pytest.mark.parametrize("amount", [0, -1, 10.5, True, "100"])
def test_deposit_rejects_invalid_amounts(tmp_path, monkeypatch, amount):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        with pytest.raises(ValueError):
            record_deposit(amount, "Invalid deposit")
        assert get_balance_cents() == 0


def test_deposit_requires_a_description(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        with pytest.raises(ValueError):
            record_deposit(100, "  ")
        assert get_balance_cents() == 0

def test_validate_stake_accepts_amount_without_deducting(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        record_deposit(10000, "Opening bankroll")

        validate_stake(1000, 1000)

        assert get_balance_cents() == 10000


@pytest.mark.parametrize(
    "amount, limit",
    [
        (0, 1000),
        (-100, 1000),
        (10.5, 1000),
        (True, 1000),
        ("100", 1000),
        (1100, 1000),
        (10001, 20000),
        (100, -1),
        (100, True),
    ],
)
def test_validate_stake_rejects_invalid_requests(
    tmp_path, monkeypatch, amount, limit
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    with app.app_context():
        record_deposit(10000, "Opening bankroll")

        with pytest.raises(ValueError):
            validate_stake(amount, limit)

        assert get_balance_cents() == 10000