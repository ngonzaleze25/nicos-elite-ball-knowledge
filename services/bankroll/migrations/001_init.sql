CREATE TABLE bankroll_transactions (
    id INT IDENTITY(1,1) PRIMARY KEY,
    transaction_type NVARCHAR(20) NOT NULL
        CHECK (transaction_type IN (
            'deposit',
            'stake',
            'payout',
            'refund',
            'withdrawal'
        )),
        amount_cents INTEGER NOT NULL,
    description NVARCHAR(MAX) NOT NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_bankroll_transactions_amount_sign CHECK (
        (transaction_type IN ('deposit', 'payout', 'refund')
            AND amount_cents > 0)
        OR
        (transaction_type IN ('stake', 'withdrawal')
            AND amount_cents < 0)
    )
);
