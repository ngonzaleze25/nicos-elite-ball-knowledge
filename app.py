import os
from decimal import Decimal, InvalidOperation

from bankroll.ledger import get_balance_cents, record_deposit
from database import init_app, init_db
from flask import Flask, redirect, render_template, request, url_for


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

    init_app(app)
    with app.app_context():
        init_db()

    @app.get("/")
    def home():
        balance_euros = Decimal(get_balance_cents()) / 100
        return render_template("index.html", balance_euros=balance_euros)

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
                error="Enter a positive euro amount with at most two decimal places and a description.",
            ), 400

        return redirect(url_for("home"))

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"

    app.run(host="0.0.0.0", port=port, debug=debug_mode)
