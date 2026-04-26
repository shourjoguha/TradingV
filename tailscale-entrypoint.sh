#!/bin/sh
# Tailscale userspace-networking entrypoint for Railway.
#
# Behaviour:
# - If TS_AUTHKEY is set, start tailscaled in userspace mode and `tailscale up`
#   so this container joins the tailnet as ephemeral host `tradingv-railway`.
#   Containers don't have CAP_NET_ADMIN by default; userspace networking
#   skirts that requirement (no /dev/net/tun needed).
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

mkdir -p "$TS_STATE_DIR" "$(dirname "$TS_SOCKET")"

echo "[entrypoint] Starting tailscaled in userspace-networking mode..."
tailscaled \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --socket="$TS_SOCKET" \
    --tun=userspace-networking \
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

# Trap signals so we cleanly stop tailscaled when the app exits.
trap 'kill -TERM $TAILSCALED_PID 2>/dev/null || true' INT TERM

echo "[entrypoint] Booting app: $*"
exec "$@"
