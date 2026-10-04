from datetime import date, datetime, timezone
from database import get_db
from journal.football_api import fetch_laliga_matches

def normalise_api_match(item):
    """Validate one API fixture and prepare its database values."""
    try:
        external_id = item["id"]
        home_team = item["homeTeam"]["name"]
        away_team = item["awayTeam"]["name"]
        api_status = item["status"]
        competition = item["competition"]["code"]
        season_start = date.fromisoformat(item["season"]["startDate"])
        kickoff = datetime.fromisoformat(
            item["utcDate"].replace("Z", "+00:00")
        )
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError("The API returned an incomplete fixture.") from error

    if (
        not isinstance(external_id, int)
        or isinstance(external_id, bool)
        or not 0 < external_id <= 9223372036854775807
    ):
        raise ValueError("The API returned an invalid match id.")

    if competition != "PD" or season_start.year != 2026:
        raise ValueError("Only LaLiga 2026–27 fixtures can be imported.")

    for team in (home_team, away_team):
        if not isinstance(team, str) or not team.strip():
            raise ValueError("The API returned an invalid team name.")

    home_team = home_team.strip()
    away_team = away_team.strip()
    if home_team.casefold() == away_team.casefold():
        raise ValueError("Home and away teams must be different.")

    if not isinstance(api_status, str) or not api_status.strip():
        raise ValueError("The API returned an invalid match status.")

    if kickoff.tzinfo is None:
        raise ValueError("API kickoff times must include a timezone.")

    home_goals = None
    away_goals = None
    status = "scheduled"

    if api_status == "FINISHED":
        try:
            home_goals = item["score"]["fullTime"]["home"]
            away_goals = item["score"]["fullTime"]["away"]
        except (KeyError, TypeError) as error:
            raise ValueError("A finished fixture has no final score.") from error

        for goals in (home_goals, away_goals):
            if (
                not isinstance(goals, int)
                or isinstance(goals, bool)
                or not 0 <= goals <= 9223372036854775807
            ):
                raise ValueError("The API returned an invalid final score.")

        status = "finished"

    return {
        "external_id": external_id,
        "home_team": home_team,
        "away_team": away_team,
        "kickoff_at": kickoff.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "status": status,
        "api_status": api_status,
    }

def import_api_matches(items):
    """Save validated fixtures atomically, using API IDs to avoid duplicates."""
    if not isinstance(items, list):
        raise ValueError("Expected a list of API fixtures.")

    matches = [normalise_api_match(item) for item in items]
    external_ids = [match["external_id"] for match in matches]
    if len(external_ids) != len(set(external_ids)):
        raise ValueError("The API response contains duplicate match ids.")

    created = 0
    updated = 0
    db = get_db()

    with db:
        db.execute("BEGIN IMMEDIATE")

        for match in matches:
            existing = db.execute(
                """
                SELECT m.*
                FROM matches AS m
                JOIN match_imports AS i ON i.match_id = m.id
                WHERE i.external_id = ?
                """,
                (match["external_id"],),
            ).fetchone()

            values = (
                match["home_team"],
                match["away_team"],
                match["kickoff_at"],
                match["home_goals"],
                match["away_goals"],
                match["status"],
            )

            if existing is None:
                cursor = db.execute(
                    """
                    INSERT INTO matches
                        (home_team, away_team, kickoff_at,
                         home_goals, away_goals, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                match_id = cursor.lastrowid
                created += 1
            else:
                match_id = existing["id"]
                protected_fields = (
                    "home_team",
                    "away_team",
                    "home_goals",
                    "away_goals",
                    "status",
                )
                changed = any(
                    existing[field] != match[field]
                    for field in protected_fields
                )

                if changed:
                    settled_bet = db.execute(
                        """
                        SELECT b.id
                        FROM bets AS b
                        JOIN bet_decisions AS d ON d.id = b.decision_id
                        WHERE d.match_id = ? AND b.status != 'open'
                        LIMIT 1
                        """,
                        (match_id,),
                    ).fetchone()
                    if settled_bet is not None:
                        raise ValueError(
                            f"API fixture {match['external_id']} changed "
                            "after settlement. Review the result manually."
                        )

                db.execute(
                    """
                    UPDATE matches
                    SET home_team = ?, away_team = ?, kickoff_at = ?,
                        home_goals = ?, away_goals = ?, status = ?
                    WHERE id = ?
                    """,
                    values + (match_id,),
                )
                updated += 1

            db.execute(
                """
                INSERT INTO match_imports
                    (external_id, match_id, api_status)
                VALUES (?, ?, ?)
                ON CONFLICT(external_id) DO UPDATE SET
                    api_status = excluded.api_status,
                    last_synced_at = CURRENT_TIMESTAMP
                """,
                (match["external_id"], match_id, match["api_status"]),
            )

    return {"created": created, "updated": updated}


def sync_laliga_matches():
    """Fetch and import fixtures when the user requests synchronisation."""
    return import_api_matches(fetch_laliga_matches())