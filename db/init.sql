IF DB_ID(N'bankroll') IS NULL
    CREATE DATABASE [bankroll];
GO

IF DB_ID(N'journal') IS NULL
    CREATE DATABASE [journal];
GO

IF SUSER_ID(N'bankroll_app') IS NULL
    CREATE LOGIN [bankroll_app] WITH PASSWORD = '$(BANKROLL_DB_PASSWORD)';
GO

USE [bankroll];
GO

IF USER_ID(N'bankroll_app') IS NULL
    CREATE USER [bankroll_app] FOR LOGIN [bankroll_app];
GO

GRANT CREATE TABLE TO [bankroll_app];
GRANT ALTER, SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [bankroll_app];
GO

USE [master];
GO

IF SUSER_ID(N'journal_app') IS NULL
    CREATE LOGIN [journal_app] WITH PASSWORD = '$(JOURNAL_DB_PASSWORD)';
GO

USE [journal];
GO

IF USER_ID(N'journal_app') IS NULL
    CREATE USER [journal_app] FOR LOGIN [journal_app];
GO

GRANT CREATE TABLE TO [journal_app];
GRANT ALTER, SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [journal_app];
GO