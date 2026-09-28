import os

from database import init_app, init_db
from flask import Flask, render_template


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
        return render_template("index.html")

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"

    app.run(host="0.0.0.0", port=port, debug=debug_mode)