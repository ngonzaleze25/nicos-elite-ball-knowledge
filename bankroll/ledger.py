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

def validate_stake(amount_cents, max_stake_cents):
    """Check a requested stake without changing the balance."""
    if (
        not isinstance(amount_cents, int)
        or isinstance(amount_cents, bool)
        or amount_cents <= 0
    ):
        raise ValueError("Stake must be a positive integer number of cents.")

    if (
        not isinstance(max_stake_cents, int)
        or isinstance(max_stake_cents, bool)
        or max_stake_cents < 0
    ):
        raise ValueError("Maximum stake must be a non-negative integer.")

    if amount_cents > max_stake_cents:
        raise ValueError("Stake exceeds the configured limit.")

    if amount_cents > get_balance_cents():
        raise ValueError("Insufficient available balance.")
    

def get_open_exposure_cents():
    """Return the total stakes committed to unsettled bets."""
    row = get_db().execute(
        """
        SELECT COALESCE(SUM(stake_cents), 0) AS exposure_cents
        FROM bets
        WHERE status = 'open'
        """
    ).fetchone()
    return row["exposure_cents"]