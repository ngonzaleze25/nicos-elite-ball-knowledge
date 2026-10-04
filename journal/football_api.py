import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MATCHES_URL = (
    "https://api.football-data.org/v4/competitions/PD/matches?season=2026"
)


def fetch_laliga_matches():
    """Fetch LaLiga 2026–27 matches without changing the database."""
    token = os.environ.get("FOOTBALL_DATA_API_TOKEN", "").strip()
    if not token:
        raise ValueError("Configure FOOTBALL_DATA_API_TOKEN before syncing.")

    request = Request(
        MATCHES_URL,
        headers={"X-Auth-Token": token},
    )

    try:
        with urlopen(request, timeout=15) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code in (401, 403):
            raise ValueError(
                "API access denied. Check your token and competition access."
            ) from error
        if error.code == 429:
            raise ValueError(
                "API request limit reached. Wait before trying again."
            ) from error
        raise ValueError(
            f"The football API returned HTTP {error.code}. Try again later."
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError(
            "Could not reach the football API. Manual tracking still works."
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("The football API returned invalid data.") from error

    if not isinstance(data, dict):
        raise ValueError("The football API returned an unexpected response.")

    matches = data.get("matches")
    if not isinstance(matches, list) or any(
        not isinstance(match, dict) for match in matches
    ):
        raise ValueError("The football API returned an invalid match list.")

    return matches