# Nico's Elite Ball Knowledge

## Purpose
A single-user Flask application for recording and analysing betting decisions for the 2026–27 LaLiga season. It retrieves fixtures and results from football-data.org, accepts manually entered bet365 and bwin decimal odds, and calculates simple Poisson probabilities and Kelly stake suggestions.

## Local Setup
Use Python 3.12. From the repository directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

If that port is occupied: PORT=5050 python app.py
Then open http://127.0.0.1:5050.
The application runs as one Flask process, binds to 0.0.0.0, and creates its database tables automatically at startup.

## Configuration and Storage
Configuration uses environment variables:
PORT: server port; default 5000.
DATA_DIR: database directory; default data inside the project.
MAX_STAKE_CENTS: maximum stake in integer cents; default 1000 (€10).
FOOTBALL_DATA_API_TOKEN: optional token required for API synchronisation.
FLASK_DEBUG: default 0; keep disabled for the normal single-process startup.

The SQLite file is DATA_DIR/betledger.sqlite3. With default settings, it is data/betledger.sqlite3.
Money is stored as integer cents. Dates are stored as ISO timestamps; the interface displays kickoff times in Madrid time.
The application starts without an API token. Saved fixtures, journal records, and bankroll operations remain available without API access

## API Synchronisation
Obtain a token from https://www.football-data.org/.
In a macOS zsh terminal, configure it without displaying it:
```bash
read -rs 'FOOTBALL_DATA_API_TOKEN?Paste your API token, then press Enter: '
export FOOTBALL_DATA_API_TOKEN
```

Start the application from the same terminal. On Matches, press Sync fixtures and results.

Synchronisation retrieves LaLiga fixtures and results for the season starting in 2026. Repeated imports update existing API-linked matches instead of creating duplicates. Synchronisation is user-triggered and does not run during application startup.

Do not commit API credentials. API errors are displayed without removing existing records.

## Using the Application

1. Record your starting bankroll on Home.
2. Synchronise fixtures and results on Matches.
3. Use Upcoming, team search, and the 7-, 14-, or 30-day window to find a fixture.
4. Expand the match and enter decimal odds for bet365 or bwin.
5. Review the Poisson estimates.
6. Choose a bookmaker and Home, Draw, or Away, then save the decision.
7. Record the actual stake, subject to your available balance and configured limit.
8. After the final score is available, settle the bet on Home. A void action refunds the stake.

My bets shows fixtures with recorded bets, placing open bets first. History shows past fixtures and results. Saving match forms preserves the active match and filters.

The Home reset button sets the available balance to zero by recording a withdrawal. It retains transaction history and open bets. Later payouts or refunds can increase the balance again.

## Backend Feature Domains

Bet Decision Journal - journal/:
It stores matches, API import mappings, bookmakers odds, decisions, and bets in SQLite. It also handles fixture synchronisation, probability estimates, odds comparison, and bet settlement.

Bankroll and Risk - bankroll/:
Maintains the transaction ledger, available balance, stake validation, open exposure, and Kelly calculations. Both domains run in the same process and share the SQLite connection provided by database.py. They are organised into separate modules but remain coupled: journal operations call bankroll helpers, exposure queries read bets, and bets reference ledger transactions. Recording a stake and settling a bet each update the bet and ledger together in one database transaction.

## Probability and Stake Calculations
The Poisson model uses completed results from the project season strictly before the selected fixture. It requires at least three earlier home games for the home team and three earlier away games for the away team.

Expected goals combine a team's scoring average with its opponent's conceding average in the relevant home/away roles. A minimum expected-goal value of 0.1 handles scoreless histories. The model returns normalised Home, Draw, and Away probabilities.

These are simple estimates from final scores, not measured xG. When history is insufficient, the interface explains why an estimate and automatic decision are unavailable.

Bookmaker-implied probability is 1 / decimal odds. The value margin is model probability minus implied probability.

Full Kelly is displayed for comparison. The suggested stake uses quarter Kelly, capped by available balance and the configured maximum stake. Actual stakes are entered by the user and validated separately.

Open stakes are deducted immediately. Winning bets receive a payout including the original stake, losing bets receive no credit, and void bets receive a refund. Already-settled bets cannot be settled again.

## Testing
Run tests and measure both core domains:
```bash
python -m pytest --cov=bankroll --cov=journal --cov-report=term-missing -q
```

Verified on 2026-10-04: 
* 155 tests passed
* 91% combined core-domain statement coverage

bankroll/kelly.py and bankroll/ledger.py each had 100% coverage.

Tests cover calculations, validation, persistence, API failures, repeated synchronisation, exclusion of future results, automatic decision probabilities, stakes, settlement, refunds, and transaction rollback.

## Scope and Limitations
* Single-user application without authentication.
* LaLiga 2026–27 and 1X2 markets only.
* Manual bet365 and bwin odds.
* No automatic bet placement, bookmaker account integration, or live-odds scraping.
* No paid shot-level xG, accumulators, or portfolio Kelly.
* One root dependency manifest: requirements.txt.
* No authored Dockerfile, CI workflow, infrastructure configuration, or public deployment for Assignment 1.

