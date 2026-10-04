import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from database import get_db

ALLOWED_BOOKMAKERS = ("bet365", "bwin")
ALLOWED_STATUSES = ("scheduled", "finished")
MADRID = ZoneInfo("Europe/Madrid")


def parse_kickoff(value):
    """Read an ISO kickoff; manual times without an offset mean Madrid time."""
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("Enter a valid kickoff date and time.")
    try:
        kickoff = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Enter a valid kickoff date and time.") from error
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=MADRID)
    return kickoff.astimezone(timezone.utc)


def in_project_season(kickoff):
    """The application's season window is 1 July 2026 through 30 June 2027."""
    return date(2026, 7, 1) <= kickoff.astimezone(MADRID).date() < date(2027, 7, 1)


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

    kickoff = parse_kickoff(kickoff_at)
    if not in_project_season(kickoff):
        raise ValueError("Kickoff must be in the 2026–27 season (July 2026–June 2027).")

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO matches (home_team, away_team, kickoff_at, status)
        VALUES (?, ?, ?, ?)
        """,
        (home_team.strip(), away_team.strip(), kickoff.isoformat(timespec="seconds"), status),
    )
    db.commit()
    return cursor.lastrowid


def list_matches():
    """Return all matches ordered by kickoff time."""
    return get_db().execute(
        """
        SELECT
            m.id, m.home_team, m.away_team, m.kickoff_at,
            m.home_goals, m.away_goals, m.status, i.api_status, i.external_id,
            EXISTS (
                SELECT 1 FROM bets AS b
                JOIN bet_decisions AS d ON d.id = b.decision_id
                WHERE d.match_id = m.id
            ) AS has_bet,
            EXISTS (
                SELECT 1 FROM bets AS b
                JOIN bet_decisions AS d ON d.id = b.decision_id
                WHERE d.match_id = m.id AND b.status = 'open'
            ) AS has_open_bet,
            CASE
                WHEN m.status = 'scheduled' AND (
                    i.api_status IS NULL OR (
                        i.api_status IN ('SCHEDULED', 'TIMED')
                        AND datetime(m.kickoff_at) > datetime('now')
                    )
                ) THEN 1 ELSE 0
            END AS can_record_stake
        FROM matches AS m
        LEFT JOIN match_imports AS i ON i.match_id = m.id
        ORDER BY m.kickoff_at, m.id
        """
    ).fetchall()


def list_visible_matches(view="upcoming", search="", days=7, now=None):
    """Select the workspace view without deleting stored historical results."""
    if view not in ("upcoming", "my_bets", "history"):
        raise ValueError("Choose Upcoming, My bets, or History.")
    if days not in (7, 14, 30):
        raise ValueError("Choose a 7, 14, or 30 day window.")
    now = now or datetime.now(timezone.utc)
    search = search.strip().casefold()
    visible = []

    for row in list_matches():
        match = dict(row)
        try:
            kickoff = parse_kickoff(match["kickoff_at"])
        except ValueError:
            continue
        if not in_project_season(kickoff):
            continue
        if search and not any(search in match[key].casefold() for key in ("home_team", "away_team")):
            continue

        available = (
            match["status"] == "scheduled"
            and kickoff > now
            and match["api_status"] in (None, "SCHEDULED", "TIMED")
        )
        if view == "upcoming" and not (available and kickoff <= now + timedelta(days=days)):
            continue
        if view == "my_bets" and not match["has_bet"]:
            continue
        if view == "history" and not (match["status"] == "finished" or kickoff <= now):
            continue

        match["can_record_stake"] = available
        match["display_kickoff"] = kickoff.astimezone(MADRID).strftime("%a %d %b %Y · %H:%M")
        match["needs_manual_score"] = (
            match["external_id"] is None and match["status"] != "finished" and kickoff <= now
        )
        match["_kickoff"] = kickoff
        visible.append(match)

    if view == "my_bets":
        visible.sort(key=lambda match: (
            not match["has_open_bet"],
            match["_kickoff"].timestamp() if match["has_open_bet"] else -match["_kickoff"].timestamp(),
        ))
    else:
        visible.sort(key=lambda match: match["_kickoff"], reverse=view == "history")
    return visible


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
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 1
        ):
            raise ValueError(
                f"{label.capitalize()} odds must be a finite number greater than 1."
            )

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
