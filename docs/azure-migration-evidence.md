# Azure migration evidence

On November 23, 2026, Bankroll applied `003_add_ledger_currency.sql`.
[Successful Azure deployment](https://github.com/ngonzaleze25/nicos-elite-ball-knowledge/actions/runs/45179977907)

## Before deployment — Azure SQL output

```text
id transaction_type amount_cents description created_at_utc
-- ---------------- ------------ ----------- --------------
1 deposit 1250 Assignment 2 migration evidence 2026-11-23T12:46:18.9004827
```

## During deployment — Bankroll startup log

```text
2026-11-23T13:05:32.680156785+00:00 stdout Applied migration: 003_add_ledger_currency.sql
```

## After deployment — Azure SQL output

```text
id transaction_type amount_cents description created_at_utc currency
-- ---------------- ------------ ----------- -------------- --------
1 deposit 1250 Assignment 2 migration evidence 2026-11-23T12:46:18.9004827 EUR
