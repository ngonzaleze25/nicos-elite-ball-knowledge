from database import get_db


def get_balance_cents():
    """Return the current balance from the signed transaction amounts."""
    row = get_db().execute(
        "SELECT COALESCE(SUM(amount_cents), 0) AS balance_cents "
        "FROM bankroll_transactions"
    ).fetchone()
    return row["balance_cents"]


def record_deposit(amount_cents, description):
    """Save a positive deposit and make it durable immediately."""
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise ValueError("Deposit amount must be an integer number of cents.")
    if amount_cents <= 0:
        raise ValueError("Deposit amount must be positive.")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Deposit description cannot be empty.")

    db = get_db()
    db.execute(
        """
        INSERT INTO bankroll_transactions
            (transaction_type, amount_cents, description)
        VALUES (?, ?, ?)
        """,
        ("deposit", amount_cents, description.strip()),
    )
    db.commit()

def list_transactions():
    """Return bankroll transactions, newest first."""
    return get_db().execute(
        """
        SELECT id, transaction_type, amount_cents, description, created_at
        FROM bankroll_transactions
        ORDER BY id DESC
        """
    ).fetchall()