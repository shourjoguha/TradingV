"""Umbrella ingest orchestrator — the single scheduled "ingester".

Wakes (launchd, nightly), checks every door for new work, starts only the
services that work needs, ingests, then tears down exactly what it started.

Doors:
  - Video queues (fitness/nutrition/learning): cheap pre-check of
    ``Videos/<door>/_ingest_queue.md``; run ``ingest_queue`` only when pending.
    The reload ping socket-activates the on-demand indexer (see
    ``ondemand_serve``); we POST ``/shutdown`` afterward for deterministic
    teardown.
  - finance (EDGAR): poll-based + idempotent. Needs the Docker Postgres
    (:5439) for the watchlist. We bring Postgres up ONLY if it's down, and
    stop it afterward ONLY if we started it — the app's Postgres is never
    touched.

Service lifecycle is guarded: nothing the orchestrator didn't start gets
stopped. Teardown runs in ``finally`` so a mid-run error still cleans up.

Run:
  python -m tools.vault_indexer.ingest.orchestrate                # all doors
  python -m tools.vault_indexer.ingest.orchestrate --doors fitness --no-finance
  python -m tools.vault_indexer.ingest.orchestrate --dry-run      # report only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger("vault-indexer.orchestrate")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

REPO_DIR = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_DIR / "docker-compose.laptop.yml"
ENV_FILE = REPO_DIR / ".env.laptop"
PG_HOST, PG_PORT = "127.0.0.1", 5439
PG_CONTAINER = "tradingview-laptop-pg"
FINANCE_RELOAD_URL = "http://127.0.0.1:8001/reload"  # finance indexer is persistent

# Faithful reproduction of the retired kb-<door>-ingest plists.
VIDEO_DOORS: dict[str, dict] = {
    "fitness":   {"queue": "Videos/fitness/_ingest_queue.md",   "video": "Videos/fitness",   "article": "Newsletters/fitness",   "port": 8002, "horizon": 24},
    "nutrition": {"queue": "Videos/nutrition/_ingest_queue.md", "video": "Videos/nutrition", "article": "Newsletters/nutrition", "port": 8003, "horizon": 24},
    "learning":  {"queue": "Videos/learning/_ingest_queue.md",  "video": "Videos/learning",  "article": "Newsletters/learning",  "port": 8004, "horizon": 36},
}
RELOAD_TIMEOUT = 300.0
DOCKER_READY_TIMEOUT = 120  # Docker Desktop cold start can take 30-60s+


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines (ignores comments/blank). os.environ wins."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _subprocess_env() -> dict[str, str]:
    """.env.laptop as base, real environment (plist-set vars) takes precedence."""
    return {**_load_env_file(ENV_FILE), **os.environ}


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _run(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    logger.info("$ %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(REPO_DIR), env=env, text=True)


def _post(url: str, timeout: float) -> str:
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:                                  # noqa: BLE001
        return f"POST {url} failed: {e}"


def _pending_count(door: str, cfg: dict, env: dict[str, str]) -> int:
    """Run ingest_queue --dry-run and count parsed queue entries."""
    cmd = [
        sys.executable, "-m", "tools.vault_indexer.ingest.ingest_queue",
        "--queue", cfg["queue"],
        "--rel-dir-video", cfg["video"],
        "--rel-dir-article", cfg["article"],
        "--dry-run",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_DIR), env=env, text=True,
            capture_output=True, timeout=120,
        )
    except Exception as e:                                  # noqa: BLE001
        logger.warning("%s: dry-run failed (%s) — treating as 0 pending", door, e)
        return 0
    if proc.returncode != 0:
        logger.warning("%s: dry-run rc=%d stderr=%s", door, proc.returncode,
                       proc.stderr.strip()[:300])
        return 0
    try:
        return len(json.loads(proc.stdout or "[]"))
    except json.JSONDecodeError:
        return 0


def _ingest_video_door(door: str, cfg: dict, env: dict[str, str]) -> None:
    cmd = [
        sys.executable, "-m", "tools.vault_indexer.ingest.ingest_queue",
        "--queue", cfg["queue"],
        "--rel-dir-video", cfg["video"],
        "--rel-dir-article", cfg["article"],
        "--reload-url", f"http://127.0.0.1:{cfg['port']}/reload",
        "--reload-timeout", str(RELOAD_TIMEOUT),
        "--default-horizon", str(cfg["horizon"]),
        "--default-model", "small",
        "--max-attempts", "3",
    ]
    _run(cmd, env)


def _docker_ready(env: dict[str, str]) -> bool:
    """True iff the Docker daemon answers `docker info`.

    The reliable readiness check: `pgrep Docker` is unreliable because Docker
    Desktop runs helper processes, not a process literally named "Docker".
    """
    try:
        return subprocess.run(
            ["docker", "info"], cwd=str(REPO_DIR), env=env,
            capture_output=True, timeout=15,
        ).returncode == 0
    except Exception:                                       # noqa: BLE001
        return False


def _ensure_docker(env: dict[str, str]) -> bool:
    """Ensure the Docker daemon is up. Returns True iff WE started it.

    When down, launches Docker Desktop headless (`open -ga Docker`) and polls
    until the daemon answers. Raises if it never comes ready.
    """
    if _docker_ready(env):
        logger.info("docker daemon already up — reusing (won't quit it)")
        return False
    logger.info("docker daemon down — launching Docker Desktop")
    _run(["open", "-ga", "Docker"], env)
    for _ in range(DOCKER_READY_TIMEOUT):
        if _docker_ready(env):
            logger.info("docker daemon ready")
            return True
        time.sleep(1)
    raise RuntimeError(
        f"Docker Desktop did not become ready within {DOCKER_READY_TIMEOUT}s"
    )


def _ensure_postgres(env: dict[str, str]) -> tuple[bool, bool]:
    """Ensure Postgres is up for the finance door.

    Returns ``(started_pg, started_docker)`` — each True iff WE started it, so
    teardown stops only what it started. When :5439 is already open, Docker is
    necessarily already up too, so both are False (pure reuse).
    """
    if _port_open(PG_HOST, PG_PORT):
        logger.info("postgres already up on :%d — reusing (won't stop it)", PG_PORT)
        return False, False
    started_docker = _ensure_docker(env)  # daemon must be ready before compose
    logger.info("postgres down — starting via docker compose")
    _run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"], env)
    for _ in range(30):
        chk = subprocess.run(
            ["docker", "exec", PG_CONTAINER, "pg_isready", "-U", "tradingview", "-q"],
            text=True, capture_output=True,
        )
        if chk.returncode == 0:
            logger.info("postgres healthy")
            return True, started_docker
        time.sleep(1)
    logger.warning("postgres did not report healthy within 30s; proceeding anyway")
    return True, started_docker


def _ingest_finance(env: dict[str, str]) -> None:
    cmd = [
        sys.executable, "-m", "tools.vault_indexer.ingest.ingest_edgar",
        "--watchlist",
    ]
    rc = _run(cmd, env).returncode
    if rc != 0:
        logger.warning("edgar ingest rc=%d", rc)
    result = _post(FINANCE_RELOAD_URL, timeout=RELOAD_TIMEOUT)
    logger.info("finance reload: %s", result)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="orchestrate")
    ap.add_argument("--doors", default="fitness,nutrition,learning",
                    help="Comma-separated video doors to consider (default all).")
    ap.add_argument("--no-finance", action="store_true",
                    help="Skip the finance/EDGAR door (and Docker Postgres).")
    ap.add_argument("--no-shutdown", action="store_true",
                    help="Don't POST /shutdown to activated indexers; let them idle-exit.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report per-door pending counts; start/ingest nothing.")
    args = ap.parse_args(argv)

    env = _subprocess_env()
    selected = [d.strip() for d in args.doors.split(",") if d.strip()]
    started_pg = False
    started_docker = False
    activated_ports: set[int] = set()

    try:
        # ---- Video doors: ingest only when the queue has pending entries ----
        for door in selected:
            cfg = VIDEO_DOORS.get(door)
            if cfg is None:
                logger.warning("unknown door %r — skipping", door)
                continue
            n = _pending_count(door, cfg, env)
            if n == 0:
                logger.info("%s: queue empty — nothing to ingest", door)
                continue
            logger.info("%s: %d pending → ingesting", door, n)
            if args.dry_run:
                continue
            _ingest_video_door(door, cfg, env)
            activated_ports.add(cfg["port"])

        # ---- finance / EDGAR door (Docker Postgres) ----
        if not args.no_finance:
            if args.dry_run:
                logger.info("finance: would run EDGAR watchlist ingest")
            else:
                # Bring-up failures (Docker won't start, etc.) skip finance but
                # must not abort the run (video doors already done) or teardown.
                try:
                    started_pg, started_docker = _ensure_postgres(env)
                    _ingest_finance(env)
                except Exception as e:                      # noqa: BLE001
                    logger.warning("finance door failed — skipping: %s", e)

        return 0
    finally:
        if not args.no_shutdown:
            for port in sorted(activated_ports):
                logger.info("teardown: POST :%d/shutdown", port)
                _post(f"http://127.0.0.1:{port}/shutdown", timeout=10)
        if started_pg:
            logger.info("teardown: stopping postgres (we started it)")
            _run(["docker", "compose", "-f", str(COMPOSE_FILE), "stop"], env)
        if started_docker:
            logger.info("teardown: quitting Docker Desktop (we started it)")
            _run(["osascript", "-e", 'quit app "Docker"'], env)


if __name__ == "__main__":
    sys.exit(main())
