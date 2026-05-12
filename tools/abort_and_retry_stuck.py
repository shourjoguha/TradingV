"""Abort orphan running analysis jobs and optionally re-submit them.

Use after a backend crash leaves jobs stuck in ``status='running'`` with
all tasks still ``pending`` (no worker is alive to drain them). Hits the
``/v1/analysis/jobs/{id}/abort`` endpoint, then optionally submits a fresh
``POST /v1/analysis/run`` with the same tickers / intervals / models so the
work isn't lost.

Usage::

    # Abort + retry every running job older than 60 minutes:
    python -m tools.abort_and_retry_stuck

    # Abort only (no retry):
    python -m tools.abort_and_retry_stuck --no-retry

    # Lower the staleness threshold:
    python -m tools.abort_and_retry_stuck --min-age-minutes 30

    # Dry run — list what would happen, take no action:
    python -m tools.abort_and_retry_stuck --dry-run

Reads ``API_URL`` (default ``http://localhost:8000``) and ``API_KEY`` from
the environment. The ``.env.laptop`` file in the repo root is sourced
automatically when present.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Iterable

import httpx


def _load_dotenv(path: Path) -> None:
    """Best-effort .env loader — sets only keys not already in os.environ."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_iso(ts: str | None) -> datetime.datetime | None:
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(ts)
    except ValueError:
        return None


def _stale_running(items: list[dict], min_age: datetime.timedelta) -> list[dict]:
    cutoff = _now_utc() - min_age
    out = []
    for j in items:
        if j.get("status") != "running":
            continue
        sub = _parse_iso(j.get("submitted_at") or j.get("created_at"))
        if sub is None or sub <= cutoff:
            out.append(j)
    return out


def _retry_payload(detail: dict) -> dict | None:
    """Reconstruct a POST /v1/analysis/run body from a job-detail response.

    The /jobs list endpoint redacts tickers/intervals/models, so we fetch
    /jobs/{id} and read them off the tasks list. Returns None when no tasks
    can be retried (job has no tasks at all).
    """
    tasks = detail.get("tasks") or []
    tickers: set[str] = set()
    intervals: set[str] = set()
    models: set[str] = set()
    for t in tasks:
        if t.get("ticker"):
            tickers.add(t["ticker"])
        if t.get("interval"):
            intervals.add(t["interval"])
        if t.get("model_id"):
            models.add(t["model_id"])
    if not tickers or not intervals:
        return None
    body: dict = {
        "tickers": sorted(tickers),
        "intervals": sorted(intervals),
    }
    if models:
        body["model_ids"] = sorted(models)
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="abort_and_retry_stuck")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("API_URL", "http://localhost:8000"),
        help="Backend base URL (default %(default)s).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("API_KEY"),
        help="API key (default $API_KEY).",
    )
    parser.add_argument(
        "--min-age-minutes",
        type=int,
        default=60,
        help="Only abort jobs older than this many minutes (default 60).",
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="Abort only, do not re-submit the work.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen, take no action.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max jobs to scan in /v1/analysis/jobs (default 200).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    _load_dotenv(repo_root / ".env.laptop")
    if args.api_key is None:
        args.api_key = os.environ.get("API_KEY")
    if not args.api_key:
        print("ERROR: API_KEY not set (env or .env.laptop)", file=sys.stderr)
        return 2

    headers = {"X-API-Key": args.api_key}
    min_age = datetime.timedelta(minutes=args.min_age_minutes)

    with httpx.Client(base_url=args.api_url, headers=headers, timeout=30.0) as client:
        listing = client.get(
            "/v1/analysis/jobs", params={"limit": args.limit}
        )
        listing.raise_for_status()
        items = listing.json()
        if not isinstance(items, list):
            items = items.get("items", [])

        stale = _stale_running(items, min_age=min_age)
        print(
            f"Found {len(stale)} running job(s) older than "
            f"{args.min_age_minutes} min."
        )
        if not stale:
            return 0

        aborted = 0
        retried = 0
        for j in stale:
            jid = j.get("id")
            sub = j.get("submitted_at") or j.get("created_at")
            print(f"\n• job {jid}  submitted={sub}")

            if args.dry_run:
                print("  [dry-run] would abort + retry")
                continue

            # 1) Fetch detail (we need it for retry params).
            detail_resp = client.get(f"/v1/analysis/jobs/{jid}")
            if detail_resp.status_code == 404:
                print("  job vanished mid-flight — skipping")
                continue
            detail_resp.raise_for_status()
            detail = detail_resp.json()
            payload = None if args.no_retry else _retry_payload(detail)

            # 2) Abort.
            abort_resp = client.post(f"/v1/analysis/jobs/{jid}/abort")
            if abort_resp.status_code == 404:
                print("  abort returned 404 — already gone")
            else:
                abort_resp.raise_for_status()
                aborted += 1
                print("  aborted ✓")

            # 3) Retry.
            if payload is None:
                if not args.no_retry:
                    print("  no retry payload (no tasks recorded) — skipped")
                continue
            run_resp = client.post("/v1/analysis/run", json=payload)
            if run_resp.status_code >= 400:
                print(f"  retry failed: HTTP {run_resp.status_code} — {run_resp.text}")
                continue
            run_data = run_resp.json()
            queue_id = run_data.get("queue_id")
            print(
                f"  re-submitted: queue_id={queue_id} "
                f"({len(payload['tickers'])} tickers × "
                f"{len(payload['intervals'])} intervals)"
            )
            retried += 1

        print()
        print(f"Aborted {aborted}, re-submitted {retried}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
