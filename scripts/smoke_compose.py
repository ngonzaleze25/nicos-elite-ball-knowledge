import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def compose(*args):
    return subprocess.check_output(["docker", "compose", *args], text=True).strip()


def origin(service, port):
    binding = compose("port", service, str(port)).splitlines()[0]
    return "http://127.0.0.1:" + binding.rsplit(":", 1)[1]


def json_request(url, body=None):
    request = Request(url)
    if body is not None:
        request = Request(
            url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
    with urlopen(request, timeout=5) as response:
        return response.status, json.load(response)


def wait_for_health(base_url):
    deadline = time.monotonic() + 90
    while True:
        try:
            status, payload = json_request(base_url + "/health")
            assert status == 200 and payload["db"] == "ok", payload
            return
        except (URLError, OSError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Health check did not recover at {base_url}") from error
            time.sleep(1)


def verify_betting(bankroll, journal, fixture, match_id, balance):
    for bookmaker in ("bet365", "bwin"):
        status, _ = json_request(journal + f"/matches/{match_id}/odds", {
            "bookmaker": bookmaker, "home_odds": 2.5, "draw_odds": 3.3, "away_odds": 4.0,
        })
        assert status == 200
    _, detail = json_request(journal + f"/matches/{match_id}/betting")
    assert len(detail["odds"]) == 2 and detail["estimate"]["home_sample_size"] == 3

    status, decision = json_request(journal + f"/matches/{match_id}/decisions", {
        "bookmaker": "bet365", "selection": "home",
    })
    assert status == 201
    _, quote = json_request(bankroll + "/kelly", {
        "decimal_odds": 2.5, "probability": detail["estimate"]["probabilities"]["home"],
    })
    assert quote["balance_cents"] == balance
    stake = {"decision_id": decision["id"], "stake_cents": 200}
    status, bet = json_request(bankroll + "/bets", stake)
    assert status == 201
    assert json_request(bankroll + "/bets", stake) == (200, bet)
    assert json_request(bankroll + "/balance")[1]["balance_cents"] == balance - 200

    settlement_url = bankroll + f"/bets/{bet['id']}/settlement"
    try:
        json_request(settlement_url, {"void": False})
    except HTTPError as error:
        assert error.code == 409
    else:
        raise AssertionError("Settlement must wait for the final score")

    finished = dict(fixture, status="finished", source_status="FINISHED", home_goals=2, away_goals=1)
    seed_fixtures([finished])
    assert json_request(settlement_url, {"void": False}) == (200, {"status": "won"})
    assert json_request(bankroll + "/balance")[1]["balance_cents"] == balance + 300


def seed_fixtures(fixtures):
    compose(
        "exec", "-T", "journal", "python", "-c",
        "from services.journal.app import save_imported_fixtures; "
        f"save_imported_fixtures({fixtures!r})",
    )


def main():
    bankroll = origin("bankroll", 8000)
    journal = origin("journal", 8000)
    wait_for_health(bankroll)
    wait_for_health(journal)
    with urlopen(origin("ui", 80), timeout=5) as response:
        assert b"deposit-form" in response.read()

    fixture = {
        "external_id": 9000000000,
        "home_team": "CI Home",
        "away_team": "CI Away",
        "kickoff_at": "2026-11-29T18:00:00+00:00",
        "source_status": "TIMED",
        "status": "scheduled",
        "home_goals": None,
        "away_goals": None,
    }
    history = [
        dict(
            fixture, external_id=fixture["external_id"] + day,
            kickoff_at=f"2026-11-{day:02}T18:00:00+00:00", source_status="FINISHED",
            status="finished", home_goals=2, away_goals=1,
        )
        for day in range(1, 4)
    ]
    seed_fixtures([fixture, *history])
    _, previous = json_request(bankroll + "/balance")
    status, deposit = json_request(
        bankroll + "/deposits", {"amount_cents": 1250, "description": "CI test deposit"}
    )
    assert status == 201 and deposit["amount_cents"] == 1250
    balance = previous["balance_cents"] + 1250
    status, healthy = json_request(journal + "/matches")
    assert status == 200 and healthy["balance_cents"] == balance, healthy
    assert healthy["bankroll_status"] == "ok"
    assert any(row["home_team"] == fixture["home_team"] for row in healthy["matches"])

    compose("stop", "bankroll")
    try:
        status, degraded = json_request(journal + "/matches")
        assert status == 200 and degraded["matches"] == healthy["matches"], degraded
        assert degraded["bankroll_status"] == "unavailable"
        assert degraded["balance_cents"] is None
        print("Journal during Bankroll stop (HTTP 200):", json.dumps({
            "bankroll_status": degraded["bankroll_status"],
            "balance_cents": degraded["balance_cents"],
            "fixture_count": len(degraded["matches"]),
        }))
    finally:
        compose("start", "bankroll")
    wait_for_health(origin("bankroll", 8000))
    _, recovered = json_request(journal + "/matches")
    assert recovered == healthy
    match_id = next(row["id"] for row in healthy["matches"] if row["status"] == "scheduled")
    verify_betting(origin("bankroll", 8000), journal, fixture, match_id, balance)
    print("Compose passed: outage recovery, persisted odds, stake debit, and final-score settlement.")


if __name__ == "__main__":
    main()
