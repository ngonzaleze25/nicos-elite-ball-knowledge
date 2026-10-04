import sqlite3
import pytest

from app import create_app
from bankroll.ledger import (
    get_balance_cents,
    get_open_exposure_cents,
    record_deposit,
)
from database import get_db
from journal.bets import list_bets, record_bet, settle_bet
from journal.decisions import record_bet_decision
from journal.matches import create_match, record_match_odds, record_match_result


def test_record_bet_deducts_stake_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_STAKE_CENTS", "1000")
    app = create_app()

    with app.app_context():
        record_deposit(10000, "Opening bankroll")
        match_id = create_match("Sevilla", "Valencia", "2026-10-10T20:00")
        record_match_odds(match_id, "bet365", 2.5, 3.4, 3.1)
        decision_id = record_bet_decision(
            match_id, "bet365", "home", 0.5
        )

        bet_id = record_bet(decision_id, 1000)

        assert get_balance_cents() == 9000

    with app.app_context():
        db = get_db()
        bet = db.execute(
            "SELECT * FROM bets WHERE id = ?",
            (bet_id,),
        ).fetchone()
        transaction = db.execute(
            "SELECT * FROM bankroll_transactions WHERE id = ?",
            (bet["stake_transaction_id"],),
        ).fetchone()

        assert get_balance_cents() == 9000
        assert bet["decision_id"] == decision_id
        assert bet["stake_cents"] == 1000
        assert bet["decimal_odds"] == 2.5
        assert bet["status"] == "open"
        assert transaction["transaction_type"] == "stake"
        assert transaction["amount_cents"] == -1000


@pytest.fixture
def funded_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_STAKE_CENTS", "1000")
    app = create_app()

    with app.app_context():
        record_deposit(10000, "Opening bankroll")
        match_id = create_match("Sevilla", "Valencia", "2026-10-10T20:00")
        record_match_odds(match_id, "bet365", 2.5, 3.4, 3.1)
        decision_id = record_bet_decision(
            match_id, "bet365", "home", 0.5
        )
        yield app, decision_id


def test_duplicate_bet_does_not_deduct_twice(funded_decision):
    app, decision_id = funded_decision
    record_bet(decision_id, 1000)

    with pytest.raises(ValueError, match="already exists"):
        record_bet(decision_id, 1000)

    assert get_balance_cents() == 9000
    db = get_db()
    assert db.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM bankroll_transactions WHERE transaction_type = 'stake'"
    ).fetchone()[0] == 1


@pytest.mark.parametrize(
    "stake, limit, message",
    [
        (1100, 1000, "configured limit"),
        (10001, 20000, "Insufficient available balance"),
    ],
)
def test_rejected_stake_leaves_money_unchanged(
    funded_decision, stake, limit, message
):
    app, decision_id = funded_decision
    app.config["MAX_STAKE_CENTS"] = limit

    with pytest.raises(ValueError, match=message):
        record_bet(decision_id, stake)

    assert get_balance_cents() == 10000
    db = get_db()
    assert db.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0
    assert db.execute(
        "SELECT COUNT(*) FROM bankroll_transactions"
    ).fetchone()[0] == 1


def test_failed_bet_insert_rolls_back_stake(funded_decision):
    app, decision_id = funded_decision
    db = get_db()

    db.execute(
        """
        CREATE TEMP TRIGGER fail_bet_insert
        BEFORE INSERT ON bets
        BEGIN
            SELECT RAISE(ABORT, 'Simulated bet insert failure');
        END;
        """
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="Simulated"):
        record_bet(decision_id, 1000)

    assert get_balance_cents() == 10000
    assert db.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0
    assert db.execute(
        "SELECT COUNT(*) FROM bankroll_transactions"
    ).fetchone()[0] == 1

    db.execute("DROP TRIGGER fail_bet_insert")
    db.commit()

    record_bet(decision_id, 1000)
    assert get_balance_cents() == 9000


def test_no_bets_means_zero_exposure(funded_decision):
    assert get_open_exposure_cents() == 0
    assert list_bets() == []


def test_open_bet_is_listed_and_counted_as_exposure(funded_decision):
    app, decision_id = funded_decision
    bet_id = record_bet(decision_id, 1000)

    bets = list_bets()

    assert len(bets) == 1
    assert bets[0]["id"] == bet_id
    assert bets[0]["home_team"] == "Sevilla"
    assert bets[0]["away_team"] == "Valencia"
    assert bets[0]["bookmaker"] == "bet365"
    assert bets[0]["selection"] == "home"
    assert bets[0]["decimal_odds"] == 2.5
    assert bets[0]["stake_cents"] == 1000
    assert bets[0]["status"] == "open"
    assert get_open_exposure_cents() == 1000
    assert get_balance_cents() == 9000


@pytest.mark.parametrize("invalid_deposit", [False, True])
def test_homepage_displays_bet_and_exposure(funded_decision, invalid_deposit):
    app, decision_id = funded_decision
    record_bet(decision_id, 1000)
    client = app.test_client()

    if invalid_deposit:
        response = client.post(
            "/deposits",
            data={"amount_euros": "invalid", "description": "Test"},
        )
        assert response.status_code == 400
    else:
        response = client.get("/")
        assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert "Current balance: <strong>€90.00</strong>" in html
    assert "Open exposure: <strong>€10.00</strong>" in html
    assert "Sevilla vs Valencia" in html
    assert "stake €10.00" in html
    assert "status: open" in html


@pytest.mark.parametrize(
    "stake, expected_status, expected_balance",
    [
        ("10.00", 302, 9000),
        ("1.001", 400, 10000),
        ("NaN", 400, 10000),
    ],
)
def test_stake_submission(
    funded_decision, stake, expected_status, expected_balance
):
    app, decision_id = funded_decision

    response = app.test_client().post(
        f"/decisions/{decision_id}/bets",
        data={"stake_euros": stake},
    )

    assert response.status_code == expected_status
    assert get_balance_cents() == expected_balance
    assert len(list_bets()) == (1 if expected_status == 302 else 0)

    if expected_status == 302:
        assert response.headers["Location"] == "/"


def test_stake_form_disappears_after_recording(funded_decision):
    app, decision_id = funded_decision
    client = app.test_client()
    form_action = f'action="/decisions/{decision_id}/bets"'

    response = client.get("/matches")
    assert response.status_code == 200
    assert form_action in response.get_data(as_text=True)

    record_bet(decision_id, 1000)

    response = client.get("/matches")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert form_action not in html
    assert "Bet already recorded" in html

@pytest.mark.parametrize(
    "score, void, expected_status, expected_balance, credit_type, credit",
    [
        ((2, 1), False, "won", 11500, "payout", 2500),
        ((0, 1), False, "lost", 9000, None, 0),
        (None, True, "void", 10000, "refund", 1000),
    ],
)
def test_settlement_updates_balance_and_exposure(
    funded_decision,
    score,
    void,
    expected_status,
    expected_balance,
    credit_type,
    credit,
):
    app, decision_id = funded_decision
    bet_id = record_bet(decision_id, 1000)
    db = get_db()

    if score is not None:
        decision = db.execute(
            "SELECT match_id FROM bet_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        record_match_result(decision["match_id"], *score)

    assert settle_bet(bet_id, void=void) == expected_status
    assert get_balance_cents() == expected_balance
    assert get_open_exposure_cents() == 0

    bet = db.execute(
        "SELECT * FROM bets WHERE id = ?", (bet_id,)
    ).fetchone()
    assert bet["status"] == expected_status
    assert bet["settled_at"] is not None

    if credit_type is None:
        assert bet["settlement_transaction_id"] is None
        assert db.execute(
            "SELECT COUNT(*) FROM bankroll_transactions"
        ).fetchone()[0] == 2
    else:
        transaction = db.execute(
            "SELECT * FROM bankroll_transactions WHERE id = ?",
            (bet["settlement_transaction_id"],),
        ).fetchone()
        assert transaction["transaction_type"] == credit_type
        assert transaction["amount_cents"] == credit

@pytest.mark.parametrize("retry_as_void", [False, True])
def test_settled_bet_cannot_credit_money_again(funded_decision, retry_as_void):
    app, decision_id = funded_decision
    bet_id = record_bet(decision_id, 1000)
    db = get_db()
    decision = db.execute(
        "SELECT match_id FROM bet_decisions WHERE id = ?",
        (decision_id,),
    ).fetchone()
    record_match_result(decision["match_id"], 2, 1)

    settle_bet(bet_id)

    with pytest.raises(ValueError, match="already settled"):
        settle_bet(bet_id, void=retry_as_void)

    assert get_balance_cents() == 11500
    assert get_open_exposure_cents() == 0
    assert list_bets()[0]["status"] == "won"
    assert db.execute(
        "SELECT COUNT(*) FROM bankroll_transactions"
    ).fetchone()[0] == 3

def test_settlement_requires_final_score(funded_decision):
    app, decision_id = funded_decision
    bet_id = record_bet(decision_id, 1000)

    with pytest.raises(ValueError, match="final score"):
        settle_bet(bet_id)

    assert get_balance_cents() == 9000
    assert get_open_exposure_cents() == 1000
    assert list_bets()[0]["status"] == "open"

def test_failed_settlement_rolls_back_payout(funded_decision):
    app, decision_id = funded_decision
    bet_id = record_bet(decision_id, 1000)
    db = get_db()
    decision = db.execute(
        "SELECT match_id FROM bet_decisions WHERE id = ?",
        (decision_id,),
    ).fetchone()
    record_match_result(decision["match_id"], 2, 1)

    db.execute(
        """
        CREATE TEMP TRIGGER fail_settlement
        BEFORE UPDATE ON bets
        WHEN NEW.status != 'open'
        BEGIN
            SELECT RAISE(ABORT, 'Simulated settlement failure');
        END;
        """
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="Simulated"):
        settle_bet(bet_id)

    assert get_balance_cents() == 9000
    assert get_open_exposure_cents() == 1000
    assert list_bets()[0]["status"] == "open"
    assert db.execute(
        "SELECT COUNT(*) FROM bankroll_transactions"
    ).fetchone()[0] == 2

    db.execute("DROP TRIGGER fail_settlement")
    db.commit()

    settle_bet(bet_id)
    assert get_balance_cents() == 11500
    assert get_open_exposure_cents() == 0

@pytest.mark.parametrize(
    "action, expected_code, expected_balance, expected_status",
    [
        ("settle", 302, 11500, "won"),
        ("void", 302, 10000, "void"),
        ("invalid", 400, 9000, "open"),
    ],
)
def test_settlement_submission(
    funded_decision,
    action,
    expected_code,
    expected_balance,
    expected_status,
):
    app, decision_id = funded_decision
    bet_id = record_bet(decision_id, 1000)
    client = app.test_client()

    if action == "settle":
        decision = get_db().execute(
            "SELECT match_id FROM bet_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        score_response = client.post(
            f"/matches/{decision['match_id']}/result",
            data={"home_goals": "2", "away_goals": "1"},
        )
        assert score_response.status_code == 302

    response = client.post(
        f"/bets/{bet_id}/settlement",
        data={"action": action},
    )

    assert response.status_code == expected_code
    assert get_balance_cents() == expected_balance
    assert list_bets()[0]["status"] == expected_status

    home = client.get("/")
    assert home.status_code == 200
    form_action = f'action="/bets/{bet_id}/settlement"'
    assert (form_action in home.get_data(as_text=True)) == (
        expected_status == "open"
    )

def test_reset_route_keeps_open_bet_and_refund_working(funded_decision):
    app, decision_id = funded_decision
    bet_id = record_bet(decision_id, 1000)
    client = app.test_client()
    assert client.get("/bankroll/reset").status_code == 405
    response = client.post("/bankroll/reset", follow_redirects=True)
    assert response.status_code == 200
    assert "Current balance: <strong>€0.00</strong>" in response.get_data(as_text=True)
    assert get_open_exposure_cents() == 1000
    assert list_bets()[0]["status"] == "open"
    assert settle_bet(bet_id, void=True) == "void"
    assert get_balance_cents() == 1000
