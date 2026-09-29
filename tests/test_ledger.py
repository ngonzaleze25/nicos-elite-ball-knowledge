import pytest

from app import create_app
from bankroll.ledger import get_balance_cents, record_deposit
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
