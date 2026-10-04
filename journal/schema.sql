CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    kickoff_at TEXT NOT NULL,
    home_goals INTEGER,
    away_goals INTEGER,
    status TEXT NOT NULL
        CHECK (status IN ('scheduled', 'finished'))
);

CREATE TABLE IF NOT EXISTS match_odds (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL
        REFERENCES matches(id),
    bookmaker TEXT NOT NULL
        CHECK (bookmaker IN ('bet365', 'bwin')),
    home_odds REAL NOT NULL
        CHECK (home_odds > 1),
    draw_odds REAL NOT NULL
        CHECK (draw_odds > 1),
    away_odds REAL NOT NULL
        CHECK (away_odds > 1),
    UNIQUE (match_id, bookmaker)
);

CREATE TABLE IF NOT EXISTS bet_decisions (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL
        REFERENCES matches(id),
    bookmaker TEXT NOT NULL
        CHECK (bookmaker IN ('bet365', 'bwin')),
    selection TEXT NOT NULL
        CHECK (selection IN ('home', 'draw', 'away')),
    model_probability REAL NOT NULL
        CHECK (model_probability >= 0 AND model_probability <= 1),
    decimal_odds REAL NOT NULL
        CHECK (decimal_odds > 1),
    implied_probability REAL NOT NULL
        CHECK (implied_probability >= 0 AND implied_probability <= 1),
    value_margin REAL NOT NULL,
    recommendation TEXT NOT NULL
        CHECK (recommendation IN ('possible_value', 'no_value')),
    full_kelly_stake_cents INTEGER NOT NULL DEFAULT 0
        CHECK (full_kelly_stake_cents >= 0),
    quarter_kelly_stake_cents INTEGER NOT NULL DEFAULT 0
        CHECK (quarter_kelly_stake_cents >= 0),
    recommended_stake_cents INTEGER NOT NULL DEFAULT 0
        CHECK (recommended_stake_cents >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (match_id, bookmaker, selection)
);

CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY,
    decision_id INTEGER NOT NULL UNIQUE
        REFERENCES bet_decisions(id),
    stake_cents INTEGER NOT NULL
        CHECK (stake_cents > 0),
    decimal_odds REAL NOT NULL
        CHECK (decimal_odds > 1),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'won', 'lost', 'void')),
    stake_transaction_id INTEGER NOT NULL UNIQUE
        REFERENCES bankroll_transactions(id),
    settlement_transaction_id INTEGER UNIQUE
        REFERENCES bankroll_transactions(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS match_imports (
    external_id INTEGER PRIMARY KEY
        CHECK (external_id > 0),
    match_id INTEGER NOT NULL UNIQUE
        REFERENCES matches(id),
    api_status TEXT NOT NULL,
    last_synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);