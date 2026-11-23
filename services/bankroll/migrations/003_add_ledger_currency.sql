ALTER TABLE dbo.bankroll_transactions
ADD currency CHAR(3) NOT NULL
    CONSTRAINT DF_bankroll_transactions_currency DEFAULT ('EUR') WITH VALUES;
