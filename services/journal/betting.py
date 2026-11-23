from contextlib import closing
from decimal import Decimal

from flask import Blueprint, request
from pymssql import Error, IntegrityError

from services.journal.database import get_connection
from services.journal.probability import estimate_from_history

betting = Blueprint("journal_betting", __name__)
BOOKMAKERS = ("bet365", "bwin")
SELECTIONS = ("home", "draw", "away")
UNAVAILABLE = {"error": "Journal database unavailable. Try again shortly."}


def read_match(cursor, match_id):
    if not 1 <= match_id <= 2_147_483_647:
        return None
    cursor.execute("""
        SELECT id, home_team, away_team, kickoff_at
        FROM dbo.matches WHERE id = %s AND external_id IS NOT NULL;
    """, (match_id,))
    return cursor.fetchone()


def odds_for_match(cursor, match_id):
    cursor.execute("""
        SELECT bookmaker, home_odds, draw_odds, away_odds
        FROM dbo.match_odds WHERE match_id = %s ORDER BY bookmaker;
    """, (match_id,))
    return cursor.fetchall()


def read_estimate(cursor, match):
    if match["kickoff_at"] is None:
        raise ValueError("A confirmed kickoff is needed to estimate probabilities.")
    cursor.execute("""
        SELECT home_team, away_team, home_goals, away_goals
        FROM dbo.matches
        WHERE external_id IS NOT NULL AND status = 'finished'
          AND kickoff_at < %s AND home_goals IS NOT NULL AND away_goals IS NOT NULL
          AND (home_team = %s OR away_team = %s);
    """, (match["kickoff_at"], match["home_team"], match["away_team"]))
    results = cursor.fetchall()
    return estimate_from_history(
        [row for row in results if row["home_team"] == match["home_team"]],
        [row for row in results if row["away_team"] == match["away_team"]],
    )


@betting.get("/matches/<int:match_id>/betting")
def match_betting(match_id):
    try:
        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            match = read_match(cursor, match_id)
            if match is None:
                return {"error": "Fixture not found."}, 404
            odds = odds_for_match(cursor, match_id)
            cursor.execute("""
                SELECT id, bookmaker, selection, decimal_odds, model_probability
                FROM dbo.bet_decisions WHERE match_id = %s ORDER BY id DESC;
            """, (match_id,))
            decisions = cursor.fetchall()
            try:
                estimate = read_estimate(cursor, match)
            except ValueError as error:
                return {"odds": odds, "decisions": decisions, "estimate": None, "estimate_message": str(error)}
    except Error:
        return UNAVAILABLE, 503
    return {"odds": odds, "decisions": decisions, "estimate": estimate, "estimate_message": None}


@betting.post("/matches/<int:match_id>/odds")
def record_odds(match_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("bookmaker") not in BOOKMAKERS:
        return {"error": "Choose bet365 or bwin."}, 400
    values = [data.get(f"{selection}_odds") for selection in SELECTIONS]
    if not all(type(value) in (int, float) and 1.0001 <= value <= 10000 for value in values):
        return {"error": "Each decimal odd must be between 1.0001 and 10000."}, 400
    try:
        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            if read_match(cursor, match_id) is None:
                return {"error": "Fixture not found."}, 404
            cursor.execute("""
                MERGE dbo.match_odds WITH (HOLDLOCK) AS current_odds
                USING (VALUES (%s, %s, %s, %s, %s)) AS incoming
                    (match_id, bookmaker, home_odds, draw_odds, away_odds)
                ON current_odds.match_id = incoming.match_id AND current_odds.bookmaker = incoming.bookmaker
                WHEN MATCHED THEN UPDATE SET home_odds = incoming.home_odds,
                    draw_odds = incoming.draw_odds, away_odds = incoming.away_odds
                WHEN NOT MATCHED THEN INSERT (match_id, bookmaker, home_odds, draw_odds, away_odds)
                    VALUES (incoming.match_id, incoming.bookmaker, incoming.home_odds,
                            incoming.draw_odds, incoming.away_odds);
            """, (match_id, data["bookmaker"], *(Decimal(str(value)) for value in values)))
            connection.commit()
    except Error:
        return UNAVAILABLE, 503
    return {"bookmaker": data["bookmaker"]}


@betting.post("/matches/<int:match_id>/decisions")
def record_decision(match_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Send a JSON object."}, 400
    bookmaker, selection = data.get("bookmaker"), data.get("selection")
    if bookmaker not in BOOKMAKERS or selection not in SELECTIONS:
        return {"error": "Choose a bookmaker and an outcome."}, 400
    try:
        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            match = read_match(cursor, match_id)
            if match is None:
                return {"error": "Fixture not found."}, 404
            odds = next((row for row in odds_for_match(cursor, match_id) if row["bookmaker"] == bookmaker), None)
            if odds is None:
                return {"error": "Record odds for that bookmaker first."}, 409
            probability = read_estimate(cursor, match)["probabilities"][selection]
            cursor.execute("""
                INSERT INTO dbo.bet_decisions (match_id, bookmaker, selection, decimal_odds, model_probability)
                OUTPUT INSERTED.id
                VALUES (%s, %s, %s, %s, %s);
            """, (match_id, bookmaker, selection, odds[f"{selection}_odds"], probability))
            decision_id = cursor.fetchone()["id"]
            connection.commit()
    except ValueError as error:
        return {"error": str(error)}, 409
    except IntegrityError:
        return {"error": "This bookmaker and outcome already have a saved decision."}, 409
    except Error:
        return UNAVAILABLE, 503
    return {"id": decision_id}, 201


@betting.get("/decisions/<int:decision_id>")
def get_decision(decision_id):
    if not 1 <= decision_id <= 2_147_483_647:
        return {"error": "Decision not found."}, 404
    try:
        with closing(get_connection()) as connection, connection.cursor(as_dict=True) as cursor:
            cursor.execute("""
                SELECT d.id, d.match_id, d.selection, d.decimal_odds, m.home_team, m.away_team,
                       m.status AS match_status, m.home_goals, m.away_goals
                FROM dbo.bet_decisions AS d JOIN dbo.matches AS m ON m.id = d.match_id
                WHERE d.id = %s;
            """, (decision_id,))
            decision = cursor.fetchone()
    except Error:
        return UNAVAILABLE, 503
    if decision is None:
        return {"error": "Decision not found."}, 404
    return decision
