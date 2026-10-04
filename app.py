import os
from journal.probability import estimate_from_results
from journal.sync import sync_laliga_matches
from decimal import Decimal, InvalidOperation
from journal.bets import list_bets, record_bet, settle_bet
from bankroll.ledger import (
    get_balance_cents,
    get_open_exposure_cents,
    list_transactions,
    record_deposit,
    reset_available_balance,
)
from database import init_app, init_db
from flask import Flask, redirect, render_template, request, url_for
from journal.decisions import (
    DEFAULT_MAX_STAKE_CENTS,
    list_bet_decisions,
    record_bet_decision,
)
from journal.matches import (
    create_match,
    list_match_odds,
    list_visible_matches,
    record_match_odds,
    record_match_result,
)
from journal.odds import implied_probability


def create_app():
    app = Flask(__name__)

    data_dir = os.environ.get(
        "DATA_DIR",
        os.path.join(app.root_path, "data"),
    )
    os.makedirs(data_dir, exist_ok=True)

    app.config["DATA_DIR"] = data_dir
    app.config["DATABASE"] = os.path.join(
        data_dir,
        "betledger.sqlite3",
    )
    app.config["MAX_STAKE_CENTS"] = int(
        os.environ.get("MAX_STAKE_CENTS", str(DEFAULT_MAX_STAKE_CENTS))
    )

    init_app(app)
    with app.app_context():
        init_db()

    @app.get("/")
    def home():
        balance_euros = Decimal(get_balance_cents()) / 100
        return render_template(
                "index.html",
                balance_euros=balance_euros,
                exposure_euros=Decimal(get_open_exposure_cents()) / 100,
                bets=list_bets(),
                transactions=list_transactions(),
        )

    @app.post("/bankroll/reset")
    def reset_bankroll():
        reset_available_balance()
        return redirect(url_for("home"))

    @app.post("/deposits")
    def add_deposit():
        amount_text = request.form.get("amount_euros", "").strip()
        description = request.form.get("description", "").strip()

        try:
            amount_euros = Decimal(amount_text)
            amount_cents = amount_euros * 100
            if not amount_euros.is_finite() or amount_cents != amount_cents.to_integral_value():
                raise ValueError("Enter a positive euro amount with at most two decimal places.")
            record_deposit(int(amount_cents), description)
        except (InvalidOperation, ValueError):
            balance_euros = Decimal(get_balance_cents()) / 100
            return render_template(
                "index.html",
                balance_euros=balance_euros,
                exposure_euros=Decimal(get_open_exposure_cents()) / 100,
                bets=list_bets(),
                transactions=list_transactions(),
                error="Enter a positive euro amount with at most two decimal places and a description.",
            ), 400

        return redirect(url_for("home"))

    def _matches_page(error=None, status_code=200, message=None):
        odds_input = request.args.get("decimal_odds", "").strip()
        calculator_probability = None
        calculator_error = None

        if "decimal_odds" in request.args:
            try:
                calculator_probability = implied_probability(float(odds_input))
            except ValueError:
                calculator_error = "Enter decimal odds greater than 1."
                status_code = 400

        view = request.values.get("view", "upcoming")
        search = request.values.get("search", "").strip()
        try:
            days = int(request.values.get("days", "7"))
            matches = list_visible_matches(view, search, days)
        except ValueError as filter_error:
            view, days = "upcoming", 7
            matches = list_visible_matches(view, search, days)
            error, status_code = str(filter_error), 400
        odds_by_match = {
            match["id"]: list_match_odds(match["id"])
            for match in matches
        }
        decisions_by_match = {
            match["id"]: list_bet_decisions(match["id"])
            for match in matches
        }
        estimates_by_match = {}
        estimate_errors = {}

        for match in matches:
            try:
                estimates_by_match[match["id"]] = estimate_from_results(
                    match["id"]
                )
            except ValueError as estimate_error:
                estimate_errors[match["id"]] = str(estimate_error)

        return render_template(
            "matches.html",
            balance_euros=Decimal(get_balance_cents()) / 100,
            exposure_euros=Decimal(get_open_exposure_cents()) / 100,
            matches=matches,
            odds_by_match=odds_by_match,
            error=error,
            message=message,
            open_match=request.values.get("open_match", ""),
            selected_view=view,
            search=search,
            days=days,
            decisions_by_match=decisions_by_match,
            estimates_by_match=estimates_by_match,
            estimate_errors=estimate_errors,
            bets_by_decision={
                bet["decision_id"]: bet for bet in list_bets()
            },
            calculator_odds=odds_input,
            calculator_probability=calculator_probability,
            calculator_error=calculator_error,
        ), status_code

    @app.get("/matches")
    def matches_page():
        return _matches_page()

    def _matches_redirect():
        context = {
            "view": request.form.get("view", "upcoming"),
            "search": request.form.get("search", ""),
            "days": request.form.get("days", "7"),
        }
        open_match = request.form.get("open_match", "")
        if open_match.isdecimal():
            context["open_match"] = open_match
            context["_anchor"] = f"match-{open_match}"
        return redirect(url_for("matches_page", **context))

    @app.post("/matches")
    def add_match():
        home_team = request.form.get("home_team", "").strip()
        away_team = request.form.get("away_team", "").strip()
        kickoff_at = request.form.get("kickoff_at", "").strip()

        try:
            create_match(home_team, away_team, kickoff_at)
        except ValueError as error:
            return _matches_page(
                error=str(error),
                status_code=400,
            )

        return _matches_redirect()

    @app.post("/matches/<int:match_id>/odds")
    def add_match_odds(match_id):
        bookmaker = request.form.get("bookmaker", "").strip()
        try:
            home_odds = float(request.form.get("home_odds", "").strip())
            draw_odds = float(request.form.get("draw_odds", "").strip())
            away_odds = float(request.form.get("away_odds", "").strip())
            record_match_odds(
                match_id,
                bookmaker,
                home_odds,
                draw_odds,
                away_odds,
            )
        except (TypeError, ValueError):
            return _matches_page(
                error="Enter valid bet365 or bwin odds greater than 1.",
                status_code=400,
            )

        return _matches_redirect()

    @app.post("/matches/<int:match_id>/result")
    def add_match_result(match_id):
        try:
            home_goals = int(request.form.get("home_goals", ""))
            away_goals = int(request.form.get("away_goals", ""))
            record_match_result(match_id, home_goals, away_goals)
        except ValueError:
            return _matches_page(
                error="Enter non-negative whole-number scores for an existing match.",
                status_code=400,
            )

        return _matches_redirect()

    @app.post("/matches/<int:match_id>/decisions")
    def add_bet_decision(match_id):
        bookmaker = request.form.get("bookmaker", "").strip()
        selection = request.form.get("selection", "").strip()

        try:
            if selection not in ("home", "draw", "away"):
                raise ValueError("Choose Home, Draw, or Away.")

            estimate = estimate_from_results(match_id)
            model_probability = estimate["probabilities"][selection]

            record_bet_decision(
                match_id=match_id,
                bookmaker=bookmaker,
                selection=selection,
                model_probability=model_probability,
                max_stake_cents=app.config["MAX_STAKE_CENTS"],
            )
        except ValueError as error:
            return _matches_page(
                error=str(error),
                status_code=400,
            )

        return _matches_redirect()
    @app.post("/decisions/<int:decision_id>/bets")
    def add_bet(decision_id):
        try:
            stake_euros = Decimal(
                request.form.get("stake_euros", "").strip()
            )

            if not stake_euros.is_finite() or stake_euros <= 0:
                raise ValueError("Enter a positive, finite stake.")

            limit_euros = Decimal(app.config["MAX_STAKE_CENTS"]) / 100
            if stake_euros > limit_euros:
                raise ValueError("Stake exceeds the configured limit.")

            stake_cents = stake_euros * 100
            if stake_cents != stake_cents.to_integral_value():
                raise ValueError("Use at most two decimal places.")

            record_bet(decision_id, int(stake_cents))

        except InvalidOperation:
            return _matches_page(
                error="Enter a valid euro stake.",
                status_code=400,
            )
        except ValueError as error:
            return _matches_page(
                error=str(error),
                status_code=400,
            )

        if "view" in request.form:
            return _matches_redirect()
        return redirect(url_for("home"))
    @app.post("/bets/<int:bet_id>/settlement")
    def settle_recorded_bet(bet_id):
        action = request.form.get("action", "").strip()

        try:
            if action not in ("settle", "void"):
                raise ValueError("Choose settlement or a void refund.")

            settle_bet(bet_id, void=(action == "void"))
        except ValueError as error:
            return render_template(
                "index.html",
                balance_euros=Decimal(get_balance_cents()) / 100,
                exposure_euros=Decimal(get_open_exposure_cents()) / 100,
                bets=list_bets(),
                transactions=list_transactions(),
                error=str(error),
            ), 400

        return redirect(url_for("home"))

    @app.post("/matches/sync")
    def synchronise_matches():
        try:
            result = sync_laliga_matches()
        except ValueError as error:
            return _matches_page(
                error=str(error),
                status_code=503,
            )

        return _matches_page(
            message=(
                f"Sync complete: {result['created']} fixtures added, "
                f"{result['updated']} existing fixtures updated."
            ),
        )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"

    app.run(host="0.0.0.0", port=port, debug=debug_mode)
