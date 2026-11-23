CREATE TABLE dbo.matches (
    id INT IDENTITY(1,1) PRIMARY KEY,
    home_team NVARCHAR(120) NOT NULL,
    away_team NVARCHAR(120) NOT NULL,
    kickoff_at NVARCHAR(40) NOT NULL,
    home_goals INT NULL,
    away_goals INT NULL,
    status NVARCHAR(20) NOT NULL
        CHECK (status IN ('scheduled', 'finished'))
);