import json
import os
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError
from urllib.request import urlopen

from flask import Blueprint, request
from pymssql import Error

from services.bankroll.database import get_connection

bets = Blueprint("bankroll_bets", __name__)
UNAVAILABLE = {"error": "Bankroll database unavailable. Try again shortly."}
JOURNAL_UNAVAILABLE = {"error": "Journal is unavailable. Try again shortly."}


def fetch_decision(decision_id):
    base = os.environ["JOURNAL_URL"].rstrip("/")
    try:
        with urlopen(f"{base}/decisions/{decision_id}", timeout=2) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code != 404:
            raise
    return None


def lock_bet_changes(cursor):
    # Both bet writes lock the ledger before reading or updating bets.
    cursor.execute("""
        SELECT COALESCE(SUM(CAST(amount_cents AS BIGINT)), 0) AS balance
        FROM dbo.bankroll_transactions WITH (TABLOCKX, HOLDLOCK);
    """)
    return cursor.fetchone()["balance"]


def insert_transaction(cursor, kind, amount, description):
    cursor.execute("""
        INSERT INTO dbo.bankroll_transactions (transaction_type, amount_cents, description)
        OUTPUT INSERTED.id VALUES (%s, %s, %s);
    """, (kind, amount, description))
    return cursor.fetchone()["id"]


@bets.get("/bets")
def list_bets():
    try:
        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            cursor.execute("""
                SELECT id, decision_id, stake_cents, decimal_odds, selection, status
                FROM dbo.bets ORDER BY id DESC;
            """)
            return {"bets": cursor.fetchall()}
    except Error:
        return UNAVAILABLE, 503


@bets.post("/bets")
def record_bet():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Send a JSON object."}, 400
    decision_id, stake = data.get("decision_id"), data.get("stake_cents")
    if type(decision_id) is not int or not 1 <= decision_id <= 2_147_483_647:
        return {"error": "Choose a saved decision."}, 400
    if type(stake) is not int or not 1 <= stake <= 1000:
        return {"error": "Stake must be between €0.01 and €10.00."}, 400

    try:
        decision = fetch_decision(decision_id)
    except (OSError, ValueError, KeyError):
        return JOURNAL_UNAVAILABLE, 503
    if decision is None:
        return {"error": "Decision not found."}, 404

    try:
        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            balance = lock_bet_changes(cursor)
            cursor.execute("SELECT id, stake_cents FROM dbo.bets WHERE decision_id = %s;", (decision_id,))
            previous = cursor.fetchone()
            if previous is not None:
                if previous["stake_cents"] != stake:
                    return {"error": "A different stake is already recorded for this decision."}, 409
                return {"id": previous["id"]}

            if stake > balance:
                return {"error": "Insufficient bankroll balance."}, 409
            transaction_id = insert_transaction(cursor, "stake", -stake, f"Stake for decision {decision_id}")
            cursor.execute("""
                INSERT INTO dbo.bets (decision_id, stake_cents, decimal_odds, selection, stake_transaction_id)
                OUTPUT INSERTED.id VALUES (%s, %s, %s, %s, %s);
            """, (decision_id, stake, Decimal(decision["decimal_odds"]), decision["selection"], transaction_id))
            bet_id = cursor.fetchone()["id"]
            connection.commit()
    except Error:
        return UNAVAILABLE, 503
    return {"id": bet_id}, 201


@bets.post("/bets/<int:bet_id>/settlement")
def settle_bet(bet_id):
    if not 1 <= bet_id <= 2_147_483_647:
        return {"error": "Bet not found."}, 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get("void")) is not bool:
        return {"error": "Send a boolean void field."}, 400

    try:
        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            cursor.execute("""
                SELECT decision_id, stake_cents, decimal_odds, selection, status
                FROM dbo.bets WHERE id = %s;
            """, (bet_id,))
            bet = cursor.fetchone()
        if bet is None:
            return {"error": "Bet not found."}, 404
        if bet["status"] != "open":
            return {"error": "This bet is already settled."}, 409

        credit, kind = 0, None
        if data["void"]:
            status, credit, kind = "void", bet["stake_cents"], "refund"
        else:
            try:
                decision = fetch_decision(bet["decision_id"])
            except (OSError, ValueError, KeyError):
                return JOURNAL_UNAVAILABLE, 503
            if decision is None:
                return {"error": "The original decision is unavailable."}, 409
            home, away = decision["home_goals"], decision["away_goals"]
            if decision["match_status"] != "finished" or home is None or away is None:
                return {"error": "Sync the final score before settling this bet."}, 409
            winner = "home" if home > away else "away" if away > home else "draw"
            status = "lost"
            if bet["selection"] == winner:
                status, kind = "won", "payout"
                credit = int((bet["stake_cents"] * bet["decimal_odds"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            lock_bet_changes(cursor)
            cursor.execute("SELECT status FROM dbo.bets WHERE id = %s;", (bet_id,))
            if cursor.fetchone()["status"] != "open":
                return {"error": "This bet is already settled."}, 409
            transaction_id = None
            if kind:
                transaction_id = insert_transaction(cursor, kind, credit, f"Settlement for bet {bet_id}")
            cursor.execute("""
                UPDATE dbo.bets SET status = %s, settlement_transaction_id = %s,
                    settled_at = SYSUTCDATETIME() WHERE id = %s;
            """, (status, transaction_id, bet_id))
            connection.commit()
    except Error:
        return UNAVAILABLE, 503
    return {"status": status}
