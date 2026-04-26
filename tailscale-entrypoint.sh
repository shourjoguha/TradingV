#!/bin/sh
# Tailscale userspace-networking entrypoint for Railway.
#
# Behaviour:
# - If TS_AUTHKEY is set, start tailscaled in userspace mode and `tailscale up`
#   so this container joins the tailnet as ephemeral host `tradingv-railway`.
#   Containers don't have CAP_NET_ADMIN by default; userspace networking
#   skirts that requirement (no /dev/net/tun needed). BUT: userspace mode
#   does NOT install kernel routes — direct connections to tailnet IPs
#   from app processes will fail. We expose tailscaled's outbound HTTP
#   proxy (and SOCKS5 fallback) on :1055 and point the app at it via
#   HTTP_PROXY/HTTPS_PROXY/ALL_PROXY env vars; httpx (and most HTTP
#   clients) auto-honour those. NO_PROXY excludes localhost, the Railway
#   internal Postgres host, and Railway's own *.railway.app domain so the
#   DB connection isn't routed through the tunnel.
# - If TS_AUTHKEY is empty, skip Tailscale entirely. The app still boots,
#   the dual-backend stays one-way (Laptop → Railway only) — same as before
#   we added Tailscale support. Safe default for any environment that hasn't
#   provisioned the auth key yet.
# - Always exec the passed-in CMD (alembic + uvicorn from the Dockerfile).
#
# Required env vars:
#   TS_AUTHKEY        Tailscale ephemeral, reusable, pre-authorised auth key.
#                     Generate at https://login.tailscale.com/admin/settings/keys
#                     with "Reusable", "Ephemeral", "Pre-authorized" all on.
#                     Tag suggestion: tag:railway.
# Optional:
#   TS_HOSTNAME       Hostname this node registers as (default: tradingv-railway).

set -e

if [ -z "${TS_AUTHKEY:-}" ]; then
    echo "[entrypoint] TS_AUTHKEY not set — skipping Tailscale, booting app directly."
    exec "$@"
fi

HOSTNAME="${TS_HOSTNAME:-tradingv-railway}"
TS_STATE_DIR="${TS_STATE_DIR:-/var/lib/tailscale}"
TS_SOCKET="${TS_SOCKET:-/var/run/tailscale/tailscaled.sock}"
TS_PROXY_PORT="${TS_PROXY_PORT:-1055}"

mkdir -p "$TS_STATE_DIR" "$(dirname "$TS_SOCKET")"

echo "[entrypoint] Starting tailscaled in userspace-networking mode..."
# --outbound-http-proxy-listen exposes an HTTP CONNECT proxy that routes
# outbound traffic through the tailnet. --socks5-server adds a SOCKS5
# fallback on the same port for tools that prefer it (curl --socks5,
# Python's `socks` etc.).
tailscaled \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --socket="$TS_SOCKET" \
    --tun=userspace-networking \
    --outbound-http-proxy-listen=":${TS_PROXY_PORT}" \
    --socks5-server=":${TS_PROXY_PORT}" \
    > /tmp/tailscaled.log 2>&1 &

TAILSCALED_PID=$!

# Wait briefly for the daemon socket to be ready.
i=0
while [ ! -S "$TS_SOCKET" ] && [ $i -lt 30 ]; do
    i=$((i + 1))
    sleep 0.2
done

if [ ! -S "$TS_SOCKET" ]; then
    echo "[entrypoint] tailscaled failed to start — see /tmp/tailscaled.log:" >&2
    cat /tmp/tailscaled.log >&2 || true
    exit 1
fi

echo "[entrypoint] Joining tailnet as $HOSTNAME (ephemeral)..."
tailscale --socket="$TS_SOCKET" up \
    --authkey="$TS_AUTHKEY" \
    --hostname="$HOSTNAME" \
    --accept-dns=true

echo "[entrypoint] Tailscale up. Status:"
tailscale --socket="$TS_SOCKET" status || true

# Ensure /var/run/tailscale/tailscaled.sock is what the CLI defaults to,
# so any in-app subprocess that calls `tailscale ...` finds it.
ln -sf "$TS_SOCKET" /var/run/tailscale/tailscaled.sock 2>/dev/null || true

# Route app outbound traffic through tailscaled's local proxy.
# httpx + requests + curl all honour these env vars.
# NO_PROXY exemptions: loopback (any local-only thing), Railway's
# internal Postgres hostname pattern, and Railway's own service domains.
# Without these the DB connection (asyncpg → postgres.railway.internal)
# would be tunneled through tailscaled and fail.
export HTTP_PROXY="http://127.0.0.1:${TS_PROXY_PORT}"
export HTTPS_PROXY="http://127.0.0.1:${TS_PROXY_PORT}"
export ALL_PROXY="socks5://127.0.0.1:${TS_PROXY_PORT}"
export NO_PROXY="localhost,127.0.0.1,postgres.railway.internal,.railway.internal,.railway.app"
# Lowercase variants — some libraries (notably httpx) check both cases
# but exporting both is the safest belt-and-braces.
export http_proxy="$HTTP_PROXY"
export https_proxy="$HTTPS_PROXY"
export all_proxy="$ALL_PROXY"
export no_proxy="$NO_PROXY"

echo "[entrypoint] HTTP(S)_PROXY=$HTTP_PROXY  NO_PROXY=$NO_PROXY"

# Trap signals so we cleanly stop tailscaled when the app exits.
trap 'kill -TERM $TAILSCALED_PID 2>/dev/null || true' INT TERM

echo "[entrypoint] Booting app: $*"
exec "$@"
