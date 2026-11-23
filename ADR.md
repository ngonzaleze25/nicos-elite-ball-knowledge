# Architecture Decision Record

## 1. Use Python with Flask

Context: The application must run as one process, use SQLite, serve a web interface, and remain simple enough for me to understand and explain during the written comprehension check.  
Decision: I will use Python with Flask and server-rendered HTML templates because Flask provides the web features the project needs with a small dependency count and allows the business logic to remain separate from the routes.  
Alternatives considered: I considered Django, but its built-in administration, authentication, and larger structure are unnecessary for this single-user application. 
Consequences: Flask keeps the application small and understandable, but I must organise the two feature domains, validation, database access, and configuration myself.

## 2. Separate the Journal and Bankroll domains within one application

Context: The assignment requires two different backend domains while keeping one application process. This entry retrospectively documents the module separation already implemented in the project.
Decision: Keep fixtures, odds, probabilities, decisions, and bets in journal/, and keep the money ledger, stake validation, and Kelly calculations in bankroll/. Flask routes coordinate these modules, which share one SQLite database.
Alternatives considered: Putting all business logic in app.py would make responsibilities harder to understand and test. Deploying separate services would violate the required single-process constraint.
Consequences: The folders provide a clear starting point for a future service split, but they are not independent services today. Journal functions call bankroll helpers, exposure queries read bets, and atomic bet operations and foreign keys connect both domains.

## 3. Link Journal Records and Bank Transactions in SQLite

Context: Recording a bet must keep its stake deduction consistent with the journal, and settlement must prevent duplicate payouts. This entry retrospectively documents the implemented schema.
Decision: Use one SQLite database with six tables: matches, match_odds, bet_decisions, bets, match_imports, and bankroll_transactions. Store money as integer cents and use foreign keys, uniqueness constraints, and checks to enforce valid relationships and values.
Alternatives considered: Storing everything in one table would repeat match data and mix decisions with financial history. Separate databases would make atomic stake and settlement operations harder to coordinate and would depart from the assignment's single documented SQLite storage path.
Consequences: Each match can have multiple odds rows and decisions, an optional API import mapping, and each decision can have at most one recorded bet. A bet references a required stake transaction and an optional settlement transaction; these foreign keys cross domain boundaries, so a future service split would need to replace the shared-database relationships and atomic transactions.

## 4. Prioritise Domain Calculations and Persistent States in Tests

Context: The assignment requires at least 70% coverage of both domains' core business logic. Incorrect calculations or inconsistent financial records would undermine the application. This entry retrospectively documents the testing approach.
Decision: Use pytest and pytest-cov to test probability and Kelly calculations, validation, SQLite persistence, historical-data filtering, API synchronisation, and atomic stake and settlement operations. Use temporary databases and simulated API responses so automated tests do not require credentials or network access.
Alternatives considered: Manual browser testing alone would not reliably detect calculation errors, duplicate payouts, or partial database writes. Testing only routes would confirm page responses without adequately checking domain behaviour.
Consequences: The verified suite has 155 passing tests and 91% combined core-domain statement coverage. Flask test-client checks also cover important forms and routes, while visual layout and live API connectivity receive manual checks; browser interaction and every external API behaviour are not fully automated.

## 5. Omit Automatic Bet Placement and Bookmaker Integration
 
Context: The application supports reviewing and recording betting decisions. Automatic bet placement would require bookmaker integration, account credentials, and handling real financial actions. I considered the additional integration effort too much for this class project. Maybe after lots of use of this I could eventually implement it. 
Decision: Keep bet365 and bwin odds manually entered and record stakes only within the local journal. Do not connect bookmaker accounts or submit real bets.
Alternatives considered: Automatic bookmaker integration could reduce manual entry, but it would add external dependencies and financial-action handling beyond the intended assignment scope. Live-odds scraping would also require maintenance when bookmaker pages change.
Consequences: The application remains focused on analysis, bankroll tracking, and explaining decisions. Users must obtain prices and place any actual bets separately, so recorded odds and stakes may differ from what was available or placed with a bookmaker.

## 6. Split Journal and Bankroll into two services

Context: In Assignment 1, Journal and Bankroll ran in the same Flask app and shared one SQLite database. In Assignment 2, each service needs its own database.

Decision: Keep the same two domains. Journal will own matches, imported fixture links, odds, betting decisions, and recorded bets. Bankroll will own the money ledger. When Journal needs the available balance for a stake suggestion, it will ask Bankroll over HTTP.

Alternatives considered: I considered having the browser fetch the balance and pass it to Journal. I chose a direct HTTP call so Journal can get the balance from Bankroll, which owns the money ledger.

Consequences: If Bankroll does not respond before the timeout, Journal will show that the stake suggestion is unavailable. The user can still view matches and odds. Recording a bet and deducting its stake now touch two databases, so the single SQLite transaction from Assignment 1 can no longer cover both writes.

## 7. Data and Migration
Context: Assignment 1 stored both domains in one SQLite database. The split gives Journal and Bankroll separate SQL Server databases.

Decision: Journal owns matches and Bankroll owns ledger transactions. Each service runs its own numbered SQL files at startup and records which ones ran in schema_migrations.
Alternatives considered: I considered keeping the first-boot schema setup from Assignment 1. I chose numbered SQL migrations so each service can apply changes in order and preserve existing rows.

Consequences: Recording a bet and deducting its stake now span two databases, so one database transaction can’t protect both writes. If a migration fails, its transaction rolls back. If an already applied migration needs correcting, write a new numbered migration.

## 8. Azure Hosting and Scaling
Context: The browser needs a public URL, and the two APIs need somewhere to run after deployment.

Decision: Azure Storage hosts the static UI. Bankroll and Journal run in one Container Apps environment on Consumption, each with its own serverless SQL database. GitHub Actions deploys using OIDC.

Alternatives considered: I considered running both APIs on an always-on VM. I chose Container Apps Consumption because the APIs can scale to zero between requests. The databases use the serverless free offer, and static hosting costs depend on storage and traffic.

Consequences: After idle time, a container may need to start and its database may need to resume, so the API retries the database connection with a delay. Each app is limited to one replica while migrations run at startup. At 100× traffic, I would check request latency and database usage, move migrations to a separate deployment step before allowing multiple replicas, and raise the database capacity if measurements show it is the bottleneck.

## 9. Gate deployment on checks for both services

Context: Each service can build successfully on its own while a broken API contract or a change to the call between services still breaks the application.

Decision: Use GitHub Actions to lint, validate the system and OpenAPI documents, test the services, and enforce 70% line coverage separately for each service. Build both images and run the service seam test through Docker Compose with a temporary SQL Server.

Alternatives considered: A stub makes timeout behavior easy to reproduce in a unit test, but it cannot show whether Compose networking, SQL permissions, and both containers work together. Keep a fast unit test and a separate Compose test that stops and restarts Bankroll.

Consequences: CI uses a synthetic fixture and a test deposit. It verifies that Journal keeps showing the fixture while Bankroll is unavailable and that the balance is restored after Bankroll restarts. CI does not call football-data.org or Azure SQL. Azure behavior is checked after deployment.
