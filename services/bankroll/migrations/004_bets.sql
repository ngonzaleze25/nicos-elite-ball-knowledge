CREATE TABLE dbo.bets (
    id INT IDENTITY(1,1) PRIMARY KEY,
    decision_id INT NOT NULL UNIQUE CHECK (decision_id > 0),
    stake_cents INT NOT NULL CHECK (stake_cents BETWEEN 1 AND 1000),
    decimal_odds DECIMAL(12, 4) NOT NULL CHECK (decimal_odds > 1),
    selection VARCHAR(4) NOT NULL CHECK (selection IN ('home', 'draw', 'away')),
    status VARCHAR(4) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'won', 'lost', 'void')),
    stake_transaction_id INT NOT NULL UNIQUE REFERENCES dbo.bankroll_transactions(id),
    settlement_transaction_id INT NULL REFERENCES dbo.bankroll_transactions(id),
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    settled_at DATETIME2 NULL
);
