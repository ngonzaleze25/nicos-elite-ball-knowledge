import json
import os
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MATCHES_URL = "https://api.football-data.org/v4/competitions/PD/matches?season=2026"
SOURCE_STATUSES = {
    "SCHEDULED", "TIMED", "IN_PLAY", "PAUSED", "EXTRA_TIME",
    "PENALTY_SHOOTOUT", "FINISHED", "SUSPENDED", "POSTPONED",
    "CANCELLED", "AWARDED",
}


class FixtureFeedError(ValueError):
    """The fixture feed could not supply a valid schedule."""


class MissingFixtureToken(FixtureFeedError):
    """The server is missing the feed credential."""


def _normalize_match(item):
    try:
        external_id = item["id"]
        home = item["homeTeam"]["name"].strip()
        away = item["awayTeam"]["name"].strip()
        source_status = item["status"]
        competition = item["competition"]["code"]
        season = date.fromisoformat(item["season"]["startDate"]).year
        raw_kickoff = item.get("utcDate")
        kickoff = datetime.fromisoformat(raw_kickoff) if raw_kickoff is not None else None
        if kickoff is not None and kickoff.tzinfo is None:
            raise ValueError("Kickoff has no timezone")
        kickoff_at = kickoff.astimezone(timezone.utc).isoformat(timespec="seconds") if kickoff else None
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError) as error:
        raise FixtureFeedError("The feed returned an incomplete fixture.") from error

    if competition != "PD" or season != 2026:
        raise FixtureFeedError("The feed returned a fixture outside LaLiga 2026–27.")
    if type(external_id) is not int or not 0 < external_id <= 9_223_372_036_854_775_807:
        raise FixtureFeedError("The feed returned an invalid fixture ID.")
    if not (1 <= len(home) <= 120 and 1 <= len(away) <= 120) or home.casefold() == away.casefold():
        raise FixtureFeedError("The feed returned invalid teams.")
    if not isinstance(source_status, str) or source_status not in SOURCE_STATUSES:
        raise FixtureFeedError("The feed returned an unknown fixture status.")

    home_goals = away_goals = None
    finished = source_status in {"FINISHED", "AWARDED"}
    if finished:
        score = item.get("score")
        full_time = score.get("fullTime") if isinstance(score, dict) else None
        if isinstance(full_time, dict):
            home_goals, away_goals = full_time.get("home"), full_time.get("away")
        goals = (home_goals, away_goals)
        if not all(type(goal) is int and 0 <= goal <= 2_147_483_647 for goal in goals):
            if source_status == "FINISHED":
                raise FixtureFeedError("The feed returned a finished fixture without a valid score.")
            home_goals = away_goals = None

    return {
        "external_id": external_id,
        "home_team": home,
        "away_team": away,
        "kickoff_at": kickoff_at,
        "source_status": source_status,
        "status": "finished" if finished else "scheduled",
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


def fetch_laliga_fixtures():
    token = os.environ.get("FOOTBALL_DATA_API_TOKEN", "").strip()
    if not token:
        raise MissingFixtureToken("The LaLiga feed token has not been configured on Journal.")

    request = Request(MATCHES_URL)
    request.add_unredirected_header("X-Auth-Token", token)
    try:
        with urlopen(request, timeout=10) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code == 400:
            try:
                details = json.loads(error.read(4096))
            except (OSError, ValueError):
                details = None
            if isinstance(details, dict) and details.get("message") == "Your API token is invalid.":
                raise FixtureFeedError(
                    "Football-data.org rejected the token. Check the API key configured on Journal."
                ) from error
        if error.code in (401, 403):
            raise FixtureFeedError("The feed denied access. Check Journal's token and season access.") from error
        if error.code == 429:
            raise FixtureFeedError("The feed request limit was reached. Try again shortly.") from error
        raise FixtureFeedError(f"The LaLiga feed returned HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise FixtureFeedError("The LaLiga feed could not be reached.") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise FixtureFeedError("The LaLiga feed returned unreadable data.") from error

    items = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise FixtureFeedError("The feed returned an invalid fixture list.")
    fixtures = [_normalize_match(item) for item in items]
    if len({fixture["external_id"] for fixture in fixtures}) != len(fixtures):
        raise FixtureFeedError("The feed returned duplicate fixture IDs.")
    return fixtures
