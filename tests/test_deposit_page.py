from app import create_app
from bankroll.ledger import get_balance_cents


def test_home_page_records_deposit_and_shows_balance(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()
    client = app.test_client()

    assert "€0.00" in client.get("/").get_data(as_text=True)

    response = client.post(
        "/deposits",
        data={"amount_euros": "10.50", "description": "Opening deposit"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "€10.50" in response.get_data(as_text=True)
    with app.app_context():
        assert get_balance_cents() == 1050


def test_deposit_page_rejects_extra_fractional_cents(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/deposits",
        data={"amount_euros": "10.005", "description": "Invalid"},
    )

    assert response.status_code == 400
    assert "at most two decimal places" in response.get_data(as_text=True)
    with app.app_context():
        assert get_balance_cents() == 0
