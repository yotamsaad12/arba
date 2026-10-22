# The Arba API: FastAPI + the notification/outreach worker in one process.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
RUN pip install .

# Uploaded files live here; mount a persistent volume at /data in production.
ENV ARBA_STORAGE_DIR=/data/storage
EXPOSE 8000

# Migrate, load reference data (safe to repeat), then serve. Hosts set $PORT.
CMD alembic upgrade head \
    && python -m app.scripts.seed \
    && uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
       --proxy-headers --forwarded-allow-ips="*"
