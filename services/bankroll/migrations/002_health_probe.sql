CREATE TABLE dbo.health_probe (
    id INT PRIMARY KEY,
    checked_at DATETIME2 NOT NULL
);

INSERT INTO dbo.health_probe (id, checked_at)
VALUES (1, SYSUTCDATETIME());