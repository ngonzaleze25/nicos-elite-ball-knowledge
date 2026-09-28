CREATE TABLE IF NOT EXISTS bankroll_transactions (
    id INTEGER PRIMARY KEY,
    transaction_type TEXT NOT NULL
        CHECK (transaction_type IN (
            'deposit',
            'stake',
            'payout',
            'refund',
            'withdrawal'
        )),
    amount_cents INTEGER NOT NULL
        CHECK (
            (transaction_type IN ('deposit', 'payout', 'refund')
                AND amount_cents > 0)
            OR
            (transaction_type IN ('stake', 'withdrawal')
                AND amount_cents < 0)
        ),
    description TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);