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

