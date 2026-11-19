FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py database.py migrate.py kelly.py /app/services/bankroll/
COPY migrations/ /app/services/bankroll/migrations/

RUN useradd --system --no-create-home appuser
USER appuser

CMD ["sh", "-c", "exec python -m flask --app services.bankroll.app:create_app run --host 0.0.0.0 --port \"${PORT:-8000}\""]

