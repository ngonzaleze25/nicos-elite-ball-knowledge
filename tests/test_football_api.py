import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from journal import football_api


def test_fetch_matches_uses_token_and_correct_season(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "test-token")
    expected = [{"id": 123, "status": "FINISHED"}]

    def fake_urlopen(request, timeout):
        assert request.full_url == (
            "https://api.football-data.org/v4/competitions/PD/matches?season=2026"
        )
        assert request.get_header("X-auth-token") == "test-token"
        assert timeout == 15
        return BytesIO(json.dumps({"matches": expected}).encode("utf-8"))

    monkeypatch.setattr(football_api, "urlopen", fake_urlopen)

    assert football_api.fetch_laliga_matches() == expected


def test_fetch_matches_requires_token(monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_API_TOKEN", raising=False)

    def unexpected_request(*args, **kwargs):
        pytest.fail("A request must not be sent without a token.")

    monkeypatch.setattr(football_api, "urlopen", unexpected_request)

    with pytest.raises(ValueError, match="Configure"):
        football_api.fetch_laliga_matches()


@pytest.mark.parametrize(
    "failure, expected_message",
    [
        (
            HTTPError(football_api.MATCHES_URL, 401, "Unauthorized", {}, None),
            "access denied",
        ),
        (
            HTTPError(football_api.MATCHES_URL, 403, "Forbidden", {}, None),
            "access denied",
        ),
        (
            HTTPError(football_api.MATCHES_URL, 429, "Rate limit", {}, None),
            "request limit",
        ),
        (URLError("Connection unavailable"), "Could not reach"),
        (TimeoutError(), "Could not reach"),
    ],
)
def test_fetch_matches_handles_api_failures(
    monkeypatch, failure, expected_message
):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "test-token")

    def fake_urlopen(request, timeout):
        raise failure

    monkeypatch.setattr(football_api, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match=expected_message):
        football_api.fetch_laliga_matches()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"matches": [None]},
    ],
)
def test_fetch_matches_rejects_unexpected_data(monkeypatch, payload):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "test-token")

    def fake_urlopen(request, timeout):
        return BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(football_api, "urlopen", fake_urlopen)

    with pytest.raises(ValueError):
        football_api.fetch_laliga_matches()


def test_fetch_matches_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "test-token")

    def fake_urlopen(request, timeout):
        return BytesIO(b"This is not JSON")

    monkeypatch.setattr(football_api, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="invalid data"):
        football_api.fetch_laliga_matches()