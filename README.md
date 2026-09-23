# Nico's Elite Ball Knowledge

## Purpose

Nico's Elite Ball Knowledge is a single-user web application for recording and analysing sports-betting decisions during the 2026-27 LaLiga season in Spain.

The application will retrieve LaLiga fixtures and completed results from a public football-data API. The user will manually enter decimal odds from bet365 and bwin.

Using stored match results, the application will calculate simple Poisson probability estimates, compare them with the available bookmaker prices, check bankroll limits, calculate optional Kelly stake estimates, and record the final result.

The probability and stake estimates may identify possible value, but they do not guarantee that a bet will win.

## Backend feature domains

### 1. Bet Decision Journal

This domain will store:

- LaLiga matches and completed results
- Betting markets and selections
- Manually entered bet365 and bwin odds
- Poisson probability estimates
- Calculated betting metrics
- Bet status and settlement result

A user-triggered synchronisation operation will retrieve current-season LaLiga results. If the external API is unavailable, manual bet tracking will continue to work.

### 2. Bankroll and Risk

This domain will store:

- The user's euro balance
- Risk and stake limits
- Stakes
- Payouts and refunds
- An append-only transaction history
- Current financial exposure

Before recording a decision, this domain will verify that the requested stake follows the configured bankroll limits.

The application will support three staking approaches:

- Manual stake selected by the user
- Full Kelly stake shown for comparison
- Quarter Kelly stake calculated as 25% of positive full Kelly

A Kelly estimate will use the model probability, decimal odds, and available bankroll. A zero or negative Kelly result will produce a suggested stake of EUR 0. The final allowed stake cannot exceed the available balance or the user's configured stake limit. Quarter Kelly will be the default calculated option because it reduces, but does not remove, the risk created by uncertain probability estimates.

Both domains will run inside one application but remain logically separated so they could become independent services in a later assignment.

## Main constraints

- One application process and one container
- SQLite persistence for both domains
- One dependency manifest at the repository root
- Configuration through environment variables
- Spanish user interface
- LaLiga 2026-27 only
- Manual odds from bet365 and bwin only
- User-triggered match-data synchronisation
- No live-odds scraping
- No bookmaker account integration
- No automatic bet placement
- No paid shot-level xG data
- No accumulators or portfolio Kelly calculations
- No Dockerfile or CI workflow in this assignment
