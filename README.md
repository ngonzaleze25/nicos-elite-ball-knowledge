# Nico's Elite Ball Knowledge

## Purpose
A single-user Flask application for recording and analysing betting decisions for the 2026–27 LaLiga season. It retrieves fixtures and results from football-data.org, accepts manually entered bet365 and bwin decimal odds, and calculates simple Poisson probabilities and Kelly stake suggestions.

## Run Assignment 2 locally

Install Docker Desktop and start it. Enable x86/AMD64 emulation on Apple Silicon for the SQL Server image. From a clean clone, use Python 3.12 for tests and run the following in Bash or zsh from the repository root. The generated passwords are for a fresh local volume. Keep the same values when reusing that volume.

```bash
export MSSQL_SA_PASSWORD="Aa9$(openssl rand -hex 16)"
export BANKROLL_DB_PASSWORD="Aa9$(openssl rand -hex 16)"
export JOURNAL_DB_PASSWORD="Aa9$(openssl rand -hex 16)"
docker compose up --build
```

Open [the local UI](http://127.0.0.1:8080). Stop the stack with `docker compose stop` to keep its dataset. The UI uses Bankroll on port 8000 and Journal on port 8001. A local user can also load these three settings from a private file outside the repository.

### Run a single service

With the same password settings, run `docker compose up --build bankroll` or `docker compose up --build journal`. Compose starts SQL Server and runs the database initializer automatically. Check Bankroll at `http://127.0.0.1:8000/health` or Journal at `http://127.0.0.1:8001/health`. Journal can still return its fixtures when Bankroll is offline. Bankroll can still read its balance when Journal is offline.

### Fixture sync

A [football-data.org](https://www.football-data.org/) token is needed for syncing. Enter it in the terminal that starts Compose. In zsh:

```zsh
read -rs 'FOOTBALL_DATA_API_TOKEN?Football-data.org token: '
export FOOTBALL_DATA_API_TOKEN
docker compose up -d --build
```

Select **Sync LaLiga fixtures** in the UI. Sync updates the stored fixtures and scores in place using provider IDs. Confirmed kickoffs display in the browser's current time zone. The app marks unconfirmed kickoffs as **Kickoff TBC**.

### Assignment 2 CI checks

The CI workflow validates the assignment system schema and both OpenAPI contracts, lints the service code, and enforces at least 70% coverage for each service. To run the Python checks from the repository root:

```sh
python -m pip install -r requirements-ci.txt
ruff check services scripts tests/test_service_apis.py tests/test_service_migrations.py
python scripts/validate_contracts.py
python -m pytest --cov=services.bankroll --cov=services.journal \
  tests/test_bankroll_startup.py tests/test_kelly.py tests/test_journal_fixture_feed.py \
  tests/test_service_apis.py tests/test_service_migrations.py
python -m coverage report --include='services/bankroll/*' --precision=2 --fail-under=70
python -m coverage report --include='services/journal/*' --precision=2 --fail-under=70
```

CI builds both images and starts a disposable Compose project with SQL Server. It verifies a deposit, fixture lookup, Bankroll outage and recovery, saved odds and decisions, and final-score settlement without a duplicate stake debit. CI uses synthetic fixture data and does not require Azure credentials or a football-data.org token.

### Assignment 2 Azure deployment

The public website is [Nico’s Elite Ball Knowledge](https://ngonzalezeieu2024ui.z28.web.core.windows.net/).
The deployment workflow runs on pushes to `main` after changes are reviewed in a pull request. It calls the same CI workflow before publishing both images to GitHub Container Registry with their commit SHA. It then signs in through OIDC, updates the two Container Apps, checks that both health endpoints report the deployed SHA, and uploads the static UI with the Azure API URLs in `config.js`.

Initial setup in Azure for Students:

1. Confirm the subscription allows France Central. Register the App, Operational Insights, SQL, Storage and Managed Identity providers. Use resource group `rg-ngonzaleze-ieu2024`.
2. Create the Standard LRS StorageV2 account `ngonzalezeieu2024ui` and enable its static website with `index.html`.
3. Create the logical server `ngonzaleze-ieu2024-sql` and two free-offer General Purpose Gen5 serverless databases, `ngonzaleze-ieu2024-bankroll-db` and `ngonzaleze-ieu2024-journal-db`. Use 0.5–1 vCores, locally redundant backups, and AutoPause at the free limit. Allow Azure services through the SQL firewall. Create `bankroll_app` and `journal_app` in their respective databases with `db_ddladmin`, `db_datareader`, and `db_datawriter`.
4. Create the environment `ngonzaleze-ieu2024-env` with its Log Analytics workspace. Create the `ngonzaleze-ieu2024-bankroll` and `ngonzaleze-ieu2024-journal` apps on Consumption with public ingress and scales of 0–1. The workflow sets the app port to 8000.
5. Create the user-assigned identity `ngonzaleze-ieu2024-github` with Contributor on the assignment resource group only. Create GitHub OIDC credentials scoped to `ngonzaleze25/nicos-elite-ball-knowledge` on `refs/heads/main`.
6. In repository Actions settings, add `PREFIX`, `RESOURCE_GROUP`, and `UI_STORAGE` as variables. Add `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `BANKROLL_DB_PASSWORD`, `JOURNAL_DB_PASSWORD`, and `FOOTBALL_DATA_API_TOKEN` as secrets. Use the two contained-user passwords, not the SQL administrator password.

On the first run, GitHub may publish the two GHCR packages as private. If the deployment job reports that they cannot be pulled anonymously, set only the Bankroll and Journal packages to public and rerun the failed job.

## Using the split app

1. Record a test deposit in **Bankroll** and sync the LaLiga schedule.
2. In **Betting journal**, choose a fixture and save decimal odds for bet365 or bwin.
3. Review the home, draw and away estimates. Save a decision for a bookmaker and outcome.
4. Use **Calculate Kelly** on the decision to send its saved odds and probability to the Bankroll calculator.
5. Record a simulated stake. Once the imported final score is available, settle it from the score, or void the record to refund the stake.

The site is a single-user classroom demo with a shared public dataset. Use sample data. The app records journal entries and does not connect to bookmaker accounts.

## Backend feature domains

Journal owns matches, manually entered odds and saved decisions. It imports the schedule and score updates, estimates probabilities, and looks up the balance through Bankroll's HTTP API. Bankroll owns the ledger and recorded bets so stake and settlement transactions commit atomically. It validates the decision and retrieves the fixture result over HTTP before changing the ledger. The bet references the Journal decision with a plain ID.

The original Assignment 1 app remains available locally. Install `requirements.txt` in a Python 3.12 virtual environment, run `python app.py`, and open `http://127.0.0.1:5000`. It uses the legacy SQLite database and the original server-rendered pages.

## Probability and Stake Calculations
The Poisson model uses completed results from the project season strictly before the selected fixture. It requires at least three earlier home games for the home team and three earlier away games for the away team.

Expected goals combine a team's scoring average with its opponent's conceding average in the relevant home/away roles. A minimum expected-goal value of 0.1 handles scoreless histories. The model returns normalised Home, Draw, and Away probabilities.

These are simple estimates from final scores, not measured xG. When history is insufficient, the interface explains why an estimate and automatic decision are unavailable.

Bookmaker-implied probability is 1 / decimal odds. The value margin is model probability minus implied probability.

Full Kelly is displayed for comparison. The suggested stake uses quarter Kelly, capped by available balance and the split app's €10 maximum stake. Actual stakes are entered by the user and validated separately.

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

