import math
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app

from bankroll.ledger import validate_stake
from database import get_db


def record_bet(decision_id, stake_cents):
    """Save a bet and deduct its stake in one transaction."""
    if (
        not isinstance(decision_id, int)
        or isinstance(decision_id, bool)
        or decision_id <= 0
    ):
        raise ValueError("Decision id must be a positive integer.")

    db = get_db()

    with db:
        db.execute("BEGIN IMMEDIATE")

        decision = db.execute(
            """
            SELECT d.id, d.decimal_odds, m.status AS match_status
            FROM bet_decisions AS d
            JOIN matches AS m ON m.id = d.match_id
            WHERE d.id = ?
            """,
            (decision_id,),
        ).fetchone()

        if decision is None:
            raise ValueError("Decision does not exist.")

        if decision["match_status"] != "scheduled":
            raise ValueError("Cannot record a bet on a finished match.")

        existing_bet = db.execute(
            "SELECT id FROM bets WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()

        if existing_bet is not None:
            raise ValueError("A bet already exists for this decision.")

        decimal_odds = decision["decimal_odds"]
        if not math.isfinite(decimal_odds) or decimal_odds <= 1:
            raise ValueError("Decision odds must be finite and greater than 1.")

        validate_stake(
            stake_cents,
            current_app.config["MAX_STAKE_CENTS"],
        )

        transaction = db.execute(
            """
            INSERT INTO bankroll_transactions
                (transaction_type, amount_cents, description)
            VALUES (?, ?, ?)
            """,
            ("stake", -stake_cents, f"Stake for decision {decision_id}"),
        )

        bet = db.execute(
            """
            INSERT INTO bets
                (decision_id, stake_cents, decimal_odds, stake_transaction_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                decision_id,
                stake_cents,
                decimal_odds,
                transaction.lastrowid,
            ),
        )
        bet_id = bet.lastrowid

    return bet_id

def list_bets():
    """Return recorded bets with their match details, newest first."""
    return get_db().execute(
        """
        SELECT
            b.id,
            b.decision_id,
            b.stake_cents,
            b.decimal_odds,
            b.status,
            b.created_at,
            b.settled_at,
            d.bookmaker,
            d.selection,
            m.home_team,
            m.away_team
        FROM bets AS b
        JOIN bet_decisions AS d ON d.id = b.decision_id
        JOIN matches AS m ON m.id = d.match_id
        ORDER BY b.id DESC
        """
    ).fetchall()

def settle_bet(bet_id, void=False):
    """Settle an open bet and record any payout or refund atomically."""
    if (
        not isinstance(bet_id, int)
        or isinstance(bet_id, bool)
        or bet_id <= 0
    ):
        raise ValueError("Bet id must be a positive integer.")

    if not isinstance(void, bool):
        raise ValueError("Void must be true or false.")

    db = get_db()

    with db:
        db.execute("BEGIN IMMEDIATE")

        bet = db.execute(
            """
            SELECT
                b.*,
                d.selection,
                m.status AS match_status,
                m.home_goals,
                m.away_goals
            FROM bets AS b
            JOIN bet_decisions AS d ON d.id = b.decision_id
            JOIN matches AS m ON m.id = d.match_id
            WHERE b.id = ?
            """,
            (bet_id,),
        ).fetchone()

        if bet is None:
            raise ValueError("Bet does not exist.")

        if bet["status"] != "open":
            raise ValueError("Bet is already settled.")

        credit_cents = 0
        transaction_type = None

        if void:
            status = "void"
            credit_cents = bet["stake_cents"]
            transaction_type = "refund"
        else:
            if (
                bet["match_status"] != "finished"
                or bet["home_goals"] is None
                or bet["away_goals"] is None
            ):
                raise ValueError("Record a final score before settling.")

            if bet["home_goals"] > bet["away_goals"]:
                winner = "home"
            elif bet["home_goals"] < bet["away_goals"]:
                winner = "away"
            else:
                winner = "draw"

            if bet["selection"] == winner:
                status = "won"
                credit_cents = int(
                    (
                        Decimal(bet["stake_cents"])
                        * Decimal(str(bet["decimal_odds"]))
                    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                )
                transaction_type = "payout"
            else:
                status = "lost"

        settlement_transaction_id = None

        if credit_cents > 0:
            transaction = db.execute(
                """
                INSERT INTO bankroll_transactions
                    (transaction_type, amount_cents, description)
                VALUES (?, ?, ?)
                """,
                (
                    transaction_type,
                    credit_cents,
                    f"Settlement for bet {bet_id}: {status}",
                ),
            )
            settlement_transaction_id = transaction.lastrowid

        db.execute(
            """
            UPDATE bets
            SET status = ?,
                settlement_transaction_id = ?,
                settled_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, settlement_transaction_id, bet_id),
        )

    return status