# TradingView/Kronos backend — Railway production image.
#
# Adds Tailscale (userspace networking) so this container can join the
# operator's tailnet and reach the laptop backend privately. When
# `TS_AUTHKEY` is unset the entrypoint skips Tailscale entirely and the
# app boots normally — keeps the build safe to ship before the operator
# generates a key.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System packages: build essentials for psycopg2/asyncpg fallbacks +
# Tailscale (statically-linked, official binary).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        iptables \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
        -o /usr/share/keyrings/tailscale-archive-keyring.gpg \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
        -o /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app + entrypoint.
COPY . .
RUN chmod +x /app/tailscale-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/tailscale-entrypoint.sh"]
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
