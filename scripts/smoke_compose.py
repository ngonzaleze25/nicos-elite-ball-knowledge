import json
import subprocess
import time
from urllib.error import URLError
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
    compose(
        "exec", "-T", "journal", "python", "-c",
        "from services.journal.app import save_imported_fixtures; "
        f"save_imported_fixtures({[fixture]!r})",
    )
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
    finally:
        compose("start", "bankroll")
    wait_for_health(origin("bankroll", 8000))
    _, recovered = json_request(journal + "/matches")
    assert recovered == healthy
    print("Compose passed: UI served, SQL records persisted, and the service seam recovered.")


if __name__ == "__main__":
    main()
