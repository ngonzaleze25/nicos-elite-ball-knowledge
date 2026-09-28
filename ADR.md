# Architecture Decision Record

## 1. Use Python with Flask

Date: 2026-09-23  
Status: Decided  
Context: The application must run as one process, use SQLite, serve a web interface, and remain simple enough for me to understand and explain during the written comprehension check.  
Decision: I will use Python with Flask and server-rendered HTML templates because Flask provides the web features the project needs with a small dependency count and allows the business logic to remain separate from the routes.  
Alternatives considered: I considered Django, but its built-in administration, authentication, and larger structure are unnecessary for this single-user application. 
Consequences: Flask keeps the application small and understandable, but I must organise the two feature domains, validation, database access, and configuration myself.