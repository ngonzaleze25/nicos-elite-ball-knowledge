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