CREATE TABLE dbo.match_odds (
    match_id INT NOT NULL CHECK (match_id > 0),
    bookmaker VARCHAR(6) NOT NULL CHECK (bookmaker IN ('bet365', 'bwin')),
    home_odds DECIMAL(12, 4) NOT NULL CHECK (home_odds > 1),
    draw_odds DECIMAL(12, 4) NOT NULL CHECK (draw_odds > 1),
    away_odds DECIMAL(12, 4) NOT NULL CHECK (away_odds > 1),
    PRIMARY KEY (match_id, bookmaker)
);

CREATE TABLE dbo.bet_decisions (
    id INT IDENTITY(1,1) PRIMARY KEY,
    match_id INT NOT NULL CHECK (match_id > 0),
    bookmaker VARCHAR(6) NOT NULL CHECK (bookmaker IN ('bet365', 'bwin')),
    selection VARCHAR(4) NOT NULL CHECK (selection IN ('home', 'draw', 'away')),
    decimal_odds DECIMAL(12, 4) NOT NULL CHECK (decimal_odds > 1),
    model_probability FLOAT NOT NULL CHECK (model_probability BETWEEN 0 AND 1),
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    UNIQUE (match_id, bookmaker, selection)
);
