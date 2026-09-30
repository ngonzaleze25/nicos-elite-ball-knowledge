from database import get_db

ALLOWED_BOOKMAKERS = ("bet365", "bwin")
ALLOWED_STATUSES = ("scheduled", "finished")


def create_match(home_team, away_team, kickoff_at, status="scheduled"):
    """Insert a LaLiga match and return its id."""
    if not isinstance(home_team, str) or not home_team.strip():
        raise ValueError("Home team cannot be empty.")
    if not isinstance(away_team, str) or not away_team.strip():
        raise ValueError("Away team cannot be empty.")
    if not isinstance(kickoff_at, str) or not kickoff_at.strip():
        raise ValueError("Kickoff time cannot be empty.")
    if status not in ALLOWED_STATUSES:
        raise ValueError("Status must be 'scheduled' or 'finished'.")

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO matches (home_team, away_team, kickoff_at, status)
        VALUES (?, ?, ?, ?)
        """,
        (home_team.strip(), away_team.strip(), kickoff_at.strip(), status),
    )
    db.commit()
    return cursor.lastrowid


def list_matches():
    """Return all matches ordered by kickoff time."""
    return get_db().execute(
        """
        SELECT id, home_team, away_team, kickoff_at, home_goals, away_goals, status
        FROM matches
        ORDER BY kickoff_at, id
        """
    ).fetchall()


def record_match_odds(match_id, bookmaker, home_odds, draw_odds, away_odds):
    """Save or replace 1X2 decimal odds for one bookmaker on one match."""
    if not isinstance(match_id, int) or isinstance(match_id, bool) or match_id <= 0:
        raise ValueError("Match id must be a positive integer.")
    if bookmaker not in ALLOWED_BOOKMAKERS:
        raise ValueError("Bookmaker must be 'bet365' or 'bwin'.")

    for label, value in (
        ("home", home_odds),
        ("draw", draw_odds),
        ("away", away_odds),
    ):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 1:
            raise ValueError(f"{label.capitalize()} odds must be a number greater than 1.")

    db = get_db()
    match = db.execute(
        "SELECT id FROM matches WHERE id = ?",
        (match_id,),
    ).fetchone()
    if match is None:
        raise ValueError("Match does not exist.")

    db.execute(
        """
        INSERT INTO match_odds
            (match_id, bookmaker, home_odds, draw_odds, away_odds)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(match_id, bookmaker) DO UPDATE SET
            home_odds = excluded.home_odds,
            draw_odds = excluded.draw_odds,
            away_odds = excluded.away_odds
        """,
        (match_id, bookmaker, float(home_odds), float(draw_odds), float(away_odds)),
    )
    db.commit()


def list_match_odds(match_id):
    """Return odds rows for one match."""
    return get_db().execute(
        """
        SELECT id, match_id, bookmaker, home_odds, draw_odds, away_odds
        FROM match_odds
        WHERE match_id = ?
        ORDER BY bookmaker
        """,
        (match_id,),
    ).fetchall()

def record_match_result(match_id, home_goals, away_goals):
    if not isinstance(match_id, int) or isinstance(match_id, bool) or match_id <= 0:
        raise ValueError("Match id must be a positive integer.")

    for goals in (home_goals, away_goals):
        if not isinstance(goals, int) or isinstance(goals, bool) or goals < 0:
            raise ValueError("Goals must be non-negative integers.")

    db = get_db()
    cursor = db.execute(
        """
        UPDATE matches
        SET home_goals = ?, away_goals = ?, status = 'finished'
        WHERE id = ?
        """,
        (home_goals, away_goals, match_id),
    )
    if cursor.rowcount == 0:
        raise ValueError("Match does not exist.")

    db.commit()