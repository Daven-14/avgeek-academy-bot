FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ bot/
COPY content/ content/
COPY scripts/ scripts/
COPY landing/ landing/
COPY growth/ growth/
COPY .env.example .env.example

RUN mkdir -p data/backups data/certs_cache \
    && chmod +x scripts/backup_db.sh

EXPOSE 8080

CMD ["python", "-m", "bot"]
