# TradingView demo — read-only public showcase image.
#
# No DB, no Tailscale, no model, no alembic, no secrets. Serves baked
# JSON snapshots from /app/demo-data via FastAPI. Idle-cheap on Railway.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user for read-only intent.
RUN useradd --create-home --shell /bin/bash demo
COPY --chown=demo:demo app ./app
COPY --chown=demo:demo demo-data ./demo-data
USER demo

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
