from bankroll.kelly import calculate_kelly_stake
from bankroll.ledger import get_balance_cents
from database import get_db
from journal.matches import ALLOWED_BOOKMAKERS


ALLOWED_SELECTIONS = ("home", "draw", "away")
DEFAULT_MAX_STAKE_CENTS = 1000


def _stake_euros_to_cents(stake_euros):
    return max(0, round(stake_euros * 100))


def record_bet_decision(
    match_id,
    bookmaker,
    selection,
    model_probability,
    max_stake_cents=DEFAULT_MAX_STAKE_CENTS,
):
    if not isinstance(match_id, int) or isinstance(match_id, bool) or match_id <= 0:
        raise ValueError("Match id must be a positive integer.")
    if bookmaker not in ALLOWED_BOOKMAKERS:
        raise ValueError("Bookmaker must be 'bet365' or 'bwin'.")
    if selection not in ALLOWED_SELECTIONS:
        raise ValueError("Selection must be 'home', 'draw', or 'away'.")
    if (
        not isinstance(model_probability, (int, float))
        or isinstance(model_probability, bool)
        or model_probability < 0
        or model_probability > 1
    ):
        raise ValueError("Model probability must be between 0 and 1.")
    if (
        not isinstance(max_stake_cents, int)
        or isinstance(max_stake_cents, bool)
        or max_stake_cents < 0
    ):
        raise ValueError("Maximum stake must be a non-negative number of cents.")

    db = get_db()
    odds = db.execute(
        """
        SELECT home_odds, draw_odds, away_odds
        FROM match_odds
        WHERE match_id = ? AND bookmaker = ?
        """,
        (match_id, bookmaker),
    ).fetchone()

    if odds is None:
        raise ValueError("Odds must be recorded before making a decision.")

    decimal_odds = {
        "home": odds["home_odds"],
        "draw": odds["draw_odds"],
        "away": odds["away_odds"],
    }[selection]

    implied_probability = 1 / decimal_odds
    value_margin = model_probability - implied_probability
    recommendation = "possible_value" if value_margin > 0 else "no_value"
    balance_cents = get_balance_cents()
    balance_euros = balance_cents / 100
    full_kelly_stake_cents = _stake_euros_to_cents(
        calculate_kelly_stake(
            balance_euros,
            decimal_odds,
            model_probability,
        )
    )
    quarter_kelly_stake_cents = _stake_euros_to_cents(
        calculate_kelly_stake(
            balance_euros,
            decimal_odds,
            model_probability,
            multiplier=0.25,
        )
    )
    recommended_stake_cents = min(
        quarter_kelly_stake_cents,
        balance_cents,
        max_stake_cents,
    )

    cursor = db.execute(
        """
        INSERT INTO bet_decisions
            (
                match_id,
                bookmaker,
                selection,
                model_probability,
                decimal_odds,
                implied_probability,
                value_margin,
                recommendation,
                full_kelly_stake_cents,
                quarter_kelly_stake_cents,
                recommended_stake_cents
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id, bookmaker, selection) DO UPDATE SET
            model_probability = excluded.model_probability,
            decimal_odds = excluded.decimal_odds,
            implied_probability = excluded.implied_probability,
            value_margin = excluded.value_margin,
            recommendation = excluded.recommendation,
            full_kelly_stake_cents = excluded.full_kelly_stake_cents,
            quarter_kelly_stake_cents = excluded.quarter_kelly_stake_cents,
            recommended_stake_cents = excluded.recommended_stake_cents
        """,
        (
            match_id,
            bookmaker,
            selection,
            float(model_probability),
            decimal_odds,
            implied_probability,
            value_margin,
            recommendation,
            full_kelly_stake_cents,
            quarter_kelly_stake_cents,
            recommended_stake_cents,
        ),
    )
    db.commit()

    return cursor.lastrowid


def list_bet_decisions(match_id):
    return get_db().execute(
        """
        SELECT
            id,
            match_id,
            bookmaker,
            selection,
            model_probability,
            decimal_odds,
            implied_probability,
            value_margin,
            recommendation,
            full_kelly_stake_cents,
            quarter_kelly_stake_cents,
            recommended_stake_cents,
            created_at
        FROM bet_decisions
        WHERE match_id = ?
        ORDER BY bookmaker, selection
        """,
        (match_id,),
    ).fetchall()
