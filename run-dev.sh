#!/usr/bin/env bash
# run-dev.sh — one-shot dev launcher for the TradingView stack on macOS.
#
# Boots, in order:
#   1. Dockerised Postgres (port 5439) via docker-compose.laptop.yml
#   2. Vault indexer  (port 8001) — uvicorn tools.vault_indexer.app
#   3. Backend FastAPI (port 8000) — uvicorn app.main:app --reload
#   4. Frontend Vite dev server (port 3000)
#
# Logs stream to ./.dev-logs/{indexer,backend,frontend}.log. Ctrl-C kills
# every child cleanly.
#
# Usage:
#   ./run-dev.sh            # start everything; block until Ctrl-C
#   ./run-dev.sh --no-pg    # skip Postgres step (already running elsewhere)
#   ./run-dev.sh stop       # stop any leftover processes from a prior run
#
# Open after boot:
#   Frontend:  http://localhost:3000   (proxies /v1 + /health to :8000)
#   Backend:   http://localhost:8000/docs
#   Indexer:   http://localhost:8001/health
set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${REPO_DIR}/.dev-logs"
PID_FILE="${LOG_DIR}/run-dev.pids"
ENV_FILE="${REPO_DIR}/.env.laptop"
VENV_PY="${REPO_DIR}/venv/bin/python"
VAULT_PATH="${VAULT_PATH:-${HOME}/Documents/knowledge-vault}"

mkdir -p "${LOG_DIR}"

c_red()    { printf '\033[31m%s\033[0m' "$*"; }
c_green()  { printf '\033[32m%s\033[0m' "$*"; }
c_yellow() { printf '\033[33m%s\033[0m' "$*"; }
c_cyan()   { printf '\033[36m%s\033[0m' "$*"; }
c_dim()    { printf '\033[2m%s\033[0m'  "$*"; }
log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

kill_port() {
    local port="$1"
    local pids
    pids=$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)
    if [ -n "${pids}" ]; then
        log "$(c_yellow "stopping")  process on :${port} (pid ${pids})"
        kill ${pids} 2>/dev/null || true
        sleep 0.5
        # Forceful sweep if anything still holding the port.
        pids=$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)
        [ -n "${pids}" ] && kill -9 ${pids} 2>/dev/null || true
    fi
}

indexer_healthy() {
    curl -fsS -o /dev/null "http://127.0.0.1:8001/health" 2>/dev/null
}

stop_all() {
    log "stopping dev stack"
    kill_port 3000   # frontend
    kill_port 8000   # backend
    # The finance indexer (:8001) is launchd-managed and persistent. Only kill
    # it if THIS run spawned it (launchd's was absent). Default: leave it alone
    # so Ctrl-C / `stop` don't churn-respawn the shared indexer.
    if [ "${INDEXER_EXTERNAL:-1}" -ne 1 ]; then
        kill_port 8001
    fi
    rm -f "${PID_FILE}"
}

# Kill any prior run-dev.sh monitor loops so each invocation owns the stack
# cleanly. Without this, every restart left a zombie shell polling forever.
kill_prior_runners() {
    local self="$$"
    local victims
    # `pgrep -f` matches the script path; exclude self + parent.
    victims=$(pgrep -f run-dev.sh | grep -v -e "^${self}$" -e "^${PPID}$" || true)
    if [ -n "${victims}" ]; then
        log "$(c_yellow "stopping")  prior run-dev.sh instance(s): $(echo ${victims} | tr '\n' ' ')"
        kill ${victims} 2>/dev/null || true
        sleep 0.3
        # Force any stragglers.
        victims=$(pgrep -f run-dev.sh | grep -v -e "^${self}$" -e "^${PPID}$" || true)
        [ -n "${victims}" ] && kill -9 ${victims} 2>/dev/null || true
    fi
}

if [ "${1:-}" = "stop" ]; then
    kill_prior_runners
    stop_all
    exit 0
fi

# Sweep zombies before claiming the ports.
kill_prior_runners

SKIP_PG=0
for arg in "$@"; do
    [ "${arg}" = "--no-pg" ] && SKIP_PG=1
done

# ----- Pre-flight ------------------------------------------------------------

if [ ! -f "${VENV_PY}" ]; then
    log "$(c_red "venv not found at ${VENV_PY} — run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt")"
    exit 1
fi

# Put venv/bin on PATH so subprocesses spawned by the backend (yt-dlp,
# whisper, etc.) resolve. Without this the YouTube channel poller crashes
# the lifespan loop with FileNotFoundError: 'yt-dlp'.
export PATH="${REPO_DIR}/venv/bin:${PATH}"

if [ ! -f "${ENV_FILE}" ]; then
    log "$(c_red "${ENV_FILE} missing — copy .env.laptop.example and fill secrets")"
    exit 1
fi

if [ ! -d "${VAULT_PATH}" ]; then
    log "$(c_yellow "VAULT_PATH=${VAULT_PATH} not found — vault-indexer will refuse to boot")"
fi

if [ ! -d "${REPO_DIR}/frontend/node_modules" ]; then
    log "frontend node_modules missing — running npm install once"
    (cd "${REPO_DIR}/frontend" && npm install) || exit 1
fi

# ----- 1. Postgres ----------------------------------------------------------

if [ "${SKIP_PG}" -eq 0 ]; then
    if ! lsof -nP -iTCP:5439 -sTCP:LISTEN -t > /dev/null 2>&1; then
        log "$(c_cyan "starting")  Postgres (docker compose, port 5439)"
        (cd "${REPO_DIR}" && docker compose -f docker-compose.laptop.yml up -d) \
            > "${LOG_DIR}/postgres.log" 2>&1 || {
                log "$(c_red "Postgres boot failed — see ${LOG_DIR}/postgres.log")"
                exit 1
            }
        # Give Postgres a moment to accept connections.
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            lsof -nP -iTCP:5439 -sTCP:LISTEN -t > /dev/null 2>&1 && break
            sleep 0.5
        done
    else
        log "$(c_green "ok")        Postgres already up on :5439"
    fi
fi

# Free any stale ports from a previous run before we relaunch. NOTE: :8001 is
# intentionally NOT swept — it's the launchd-managed finance indexer; the
# indexer step below detects and reuses it instead of killing/relaunching.
kill_port 8000
kill_port 3000

# Source backend env vars into THIS shell (subshells inherit on export).
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# Apply DB migrations before booting the backend. Idempotent — fast no-op
# when already at head.
log "$(c_cyan "running")  alembic upgrade head"
(
    cd "${REPO_DIR}"
    "${VENV_PY}" -m alembic upgrade head
) > "${LOG_DIR}/alembic.log" 2>&1 || {
    log "$(c_red "alembic failed — see ${LOG_DIR}/alembic.log")"
    exit 1
}

# ----- 2. Vault indexer (port 8001) -----------------------------------------

# Multi-domain vault: scope is registry-driven. `DOMAIN=finance` makes the
# indexer read `<vault>/_domains.yaml` and derive include/exclude prefixes
# automatically — no hand-set EXCLUDE_FOLDERS needed. `INDEXER_DB_PATH` is
# set explicitly to match the launchd plist convention `cache-<domain>.db`.
# See tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md for the full registry rules.
INDEXER_DB_PATH="${INDEXER_DB_PATH:-${VAULT_PATH}/.indexer/cache-finance.db}"

# The finance indexer is normally already up under launchd (KeepAlive). Reuse
# it rather than double-spawning (which fights for :8001 and logs
# "address already in use"). Only start our own if :8001 is unhealthy.
if indexer_healthy; then
    log "$(c_green "ok")        reusing launchd finance indexer on :8001"
    INDEXER_PID=""
    INDEXER_EXTERNAL=1
else
    log "$(c_cyan "starting")  vault-indexer on :8001 (vault=${VAULT_PATH}, domain=finance, db=${INDEXER_DB_PATH})"
    (
        cd "${REPO_DIR}"
        VAULT_PATH="${VAULT_PATH}" \
        DOMAIN=finance \
        INDEXER_DB_PATH="${INDEXER_DB_PATH}" \
        "${VENV_PY}" -m uvicorn \
            tools.vault_indexer.app:app --port 8001 --host 127.0.0.1 \
            > "${LOG_DIR}/indexer.log" 2>&1
    ) &
    INDEXER_PID=$!
    INDEXER_EXTERNAL=0
fi

# ----- 3. Backend (port 8000) -----------------------------------------------

log "$(c_cyan "starting")  backend FastAPI on :8000"
(
    cd "${REPO_DIR}"
    "${VENV_PY}" -m uvicorn app.main:app \
        --host 127.0.0.1 --port 8000 \
        > "${LOG_DIR}/backend.log" 2>&1
) &
BACKEND_PID=$!

# ----- 4. Frontend (port 3000) ----------------------------------------------

log "$(c_cyan "starting")  frontend Vite dev server on :3000"
(
    cd "${REPO_DIR}/frontend"
    npm run dev > "${LOG_DIR}/frontend.log" 2>&1
) &
FRONTEND_PID=$!

echo "${INDEXER_PID} ${BACKEND_PID} ${FRONTEND_PID}" > "${PID_FILE}"

# ----- Wait for readiness ---------------------------------------------------

wait_url() {
    local url="$1"
    local label="$2"
    local tries=40
    for _ in $(seq 1 ${tries}); do
        if curl -s -o /dev/null -w '%{http_code}' "${url}" 2>/dev/null \
                | grep -qE '^(200|401|403)$'; then
            log "$(c_green "ready")     ${label}"
            return 0
        fi
        sleep 0.5
    done
    log "$(c_yellow "warning")   ${label} not ready after $((tries / 2))s"
    return 1
}

wait_url "http://localhost:8001/health"      "vault-indexer  http://localhost:8001"
wait_url "http://localhost:8000/openapi.json" "backend        http://localhost:8000/docs"
wait_url "http://localhost:3000/"             "frontend       http://localhost:3000"

cat <<EOF

$(c_green "✓ stack up")
  Frontend  $(c_cyan http://localhost:3000)
  Backend   $(c_cyan http://localhost:8000/docs)
  Indexer   $(c_cyan http://localhost:8001/health)

$(c_dim "Logs streaming to ${LOG_DIR}/*.log — tail in another terminal:")
  $(c_dim "tail -f ${LOG_DIR}/{backend,frontend,indexer}.log")

$(c_dim "Press Ctrl-C to stop everything cleanly.")
EOF

# ----- Trap + wait ----------------------------------------------------------

cleanup() {
    log "$(c_yellow "shutting down") (Ctrl-C received)"
    stop_all
    exit 0
}
trap cleanup INT TERM

# Keep the script in foreground. Re-check children every 3s; if one dies,
# log it and keep the others alive so the operator can still inspect what
# came up. Exit when ALL children are dead — no point monitoring nothing
# (this is what was leaking zombie monitor loops on every restart).
while true; do
    sleep 3
    alive_count=0
    for pair in "indexer:${INDEXER_PID}" "backend:${BACKEND_PID}" "frontend:${FRONTEND_PID}"; do
        name="${pair%%:*}"
        pid="${pair##*:}"
        # Empty pid = service is external (launchd-managed finance indexer that
        # we reused). Not ours to monitor — skip without flagging it "exited".
        [ -z "${pid}" ] && continue
        if kill -0 "${pid}" 2>/dev/null; then
            alive_count=$((alive_count + 1))
        else
            # Don't spam the same warning repeatedly.
            case " ${REPORTED_DEAD:-} " in *" ${name} "*) ;; *)
                log "$(c_red "exited")    ${name} (pid ${pid}) — see ${LOG_DIR}/${name}.log"
                REPORTED_DEAD="${REPORTED_DEAD:-} ${name}"
                ;;
            esac
        fi
    done
    if [ "${alive_count}" -eq 0 ]; then
        log "$(c_red "all services exited") — monitor loop done"
        rm -f "${PID_FILE}"
        exit 1
    fi
done
