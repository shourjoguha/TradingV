"""Retention sweeps — Phase 5 of the cost-aware iteration.

Order matters per the plan:
  1. DB sweeps (prediction_accuracy / drift_alerts / research_queries)
  2. Vault file sweeps (filings, IR transcripts, The Street rollup)
  3. POST :8001/reload to vault-indexer

Each sweep is its own callable so the operator can fire them individually
from the Retention tab.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import delete, func, select

from app.core import db as _db


logger = logging.getLogger(__name__)


# Hardcoded defaults. Operator can override via app_settings under retention.*
DEFAULT_TTL_DAYS = {
    "prediction_accuracy": 365,
    "drift_alerts_acked": 90,
    "drift_alerts_expired": 30,
    "research_queries_dismissed": 180,
    "research_queries_error": 90,
    "filings_8k": 18 * 30,  # 540 days ≈ 18 months
}

MANUAL_PURGE_CAP = 5000


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def _get_ttl(key: str, default: int) -> int:
    from app.admin import service as _svc

    val = await _svc.get_setting(f"retention.{key}", default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# -----------------------------------------------------------------------------
# DB sweeps.
# -----------------------------------------------------------------------------


async def sweep_prediction_accuracy(*, cap: Optional[int] = None) -> int:
    from app.accuracy.models import PredictionAccuracy

    days = await _get_ttl("prediction_accuracy_days", DEFAULT_TTL_DAYS["prediction_accuracy"])
    cutoff = _utc_now() - datetime.timedelta(days=days)
    async with _db.SessionLocal() as session:
        stmt = select(PredictionAccuracy).where(
            PredictionAccuracy.evaluated_at < cutoff
        )
        if cap is not None:
            stmt = stmt.limit(cap)
        rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            await session.delete(row)
        await session.commit()
    return len(rows)


async def sweep_drift_alerts(*, cap: Optional[int] = None) -> int:
    """Drop acked drift alerts whose ``acknowledged_at`` is older than the TTL.

    Unacked alerts stay forever (operator must address them). The model has
    no separate ``status='expired'`` column — rows just sit until acked.
    """
    from app.accuracy.models import DriftAlert

    acked_days = await _get_ttl(
        "drift_alerts_acked_days", DEFAULT_TTL_DAYS["drift_alerts_acked"]
    )
    cutoff = _utc_now() - datetime.timedelta(days=acked_days)
    deleted = 0
    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(DriftAlert)
                .where(
                    DriftAlert.acknowledged_at.is_not(None),
                    DriftAlert.acknowledged_at < cutoff,
                )
                .limit(cap or 10**9)
            )
        ).scalars().all()
        for row in rows:
            await session.delete(row)
            deleted += 1
        await session.commit()
    return deleted


async def sweep_research_queries(*, cap: Optional[int] = None) -> int:
    """Per-status retention matrix:
    - approved: forever (audit trail)
    - pending: forever (operator must resolve)
    - dismissed: configurable (default 180d)
    - error: configurable (default 90d)
    """
    from app.research.models import ResearchQuery

    dismissed_days = await _get_ttl(
        "research_queries_dismissed_days", DEFAULT_TTL_DAYS["research_queries_dismissed"]
    )
    error_days = await _get_ttl(
        "research_queries_error_days", DEFAULT_TTL_DAYS["research_queries_error"]
    )
    now = _utc_now()
    dismissed_cutoff = now - datetime.timedelta(days=dismissed_days)
    error_cutoff = now - datetime.timedelta(days=error_days)
    deleted = 0
    async with _db.SessionLocal() as session:
        rows = (
            await session.execute(
                select(ResearchQuery).where(
                    ((ResearchQuery.status == "dismissed") & (ResearchQuery.asked_at < dismissed_cutoff))
                    | ((ResearchQuery.status == "error") & (ResearchQuery.asked_at < error_cutoff))
                ).limit(cap or 10**9)
            )
        ).scalars().all()
        for row in rows:
            await session.delete(row)
            deleted += 1
        await session.commit()
    return deleted


# -----------------------------------------------------------------------------
# Counts (Retention tab — "current TTL, row count, oldest row" rendering).
# -----------------------------------------------------------------------------


async def list_class_status() -> list[dict]:
    """Return per-data-class summary for the Retention tab."""
    from app.accuracy.models import DriftAlert, PredictionAccuracy
    from app.research.models import ResearchQuery

    async with _db.SessionLocal() as session:
        pa_count = (
            await session.execute(select(func.count()).select_from(PredictionAccuracy))
        ).scalar() or 0
        pa_oldest = (
            await session.execute(select(func.min(PredictionAccuracy.evaluated_at)))
        ).scalar()

        da_count = (
            await session.execute(select(func.count()).select_from(DriftAlert))
        ).scalar() or 0
        da_oldest = (
            await session.execute(select(func.min(DriftAlert.flagged_at)))
        ).scalar()

        rq_total = (
            await session.execute(select(func.count()).select_from(ResearchQuery))
        ).scalar() or 0
        rq_pending = (
            await session.execute(
                select(func.count())
                .select_from(ResearchQuery)
                .where(ResearchQuery.status == "pending")
            )
        ).scalar() or 0
        rq_approved = (
            await session.execute(
                select(func.count())
                .select_from(ResearchQuery)
                .where(ResearchQuery.status == "approved")
            )
        ).scalar() or 0
        rq_dismissed = (
            await session.execute(
                select(func.count())
                .select_from(ResearchQuery)
                .where(ResearchQuery.status == "dismissed")
            )
        ).scalar() or 0
        rq_error = (
            await session.execute(
                select(func.count())
                .select_from(ResearchQuery)
                .where(ResearchQuery.status == "error")
            )
        ).scalar() or 0

    pa_ttl = await _get_ttl("prediction_accuracy_days", DEFAULT_TTL_DAYS["prediction_accuracy"])
    da_acked = await _get_ttl(
        "drift_alerts_acked_days", DEFAULT_TTL_DAYS["drift_alerts_acked"]
    )
    da_expired = await _get_ttl(
        "drift_alerts_expired_days", DEFAULT_TTL_DAYS["drift_alerts_expired"]
    )
    rq_dismissed_ttl = await _get_ttl(
        "research_queries_dismissed_days", DEFAULT_TTL_DAYS["research_queries_dismissed"]
    )
    rq_error_ttl = await _get_ttl(
        "research_queries_error_days", DEFAULT_TTL_DAYS["research_queries_error"]
    )

    return [
        {
            "key": "prediction_accuracy",
            "title": "Prediction accuracy",
            "ttl_days": pa_ttl,
            "row_count": pa_count,
            "oldest_at": pa_oldest.isoformat() if pa_oldest else None,
            "purge_endpoint": "/v1/admin/retention/prediction_accuracy/purge",
        },
        {
            "key": "drift_alerts",
            "title": "Drift alerts",
            "ttl_days": da_acked,
            "ttl_days_extra": {
                "acked": da_acked,
                "expired": da_expired,
                "unacked": "forever",
            },
            "row_count": da_count,
            "oldest_at": da_oldest.isoformat() if da_oldest else None,
            "purge_endpoint": "/v1/admin/retention/drift_alerts/purge",
        },
        {
            "key": "research_queries",
            "title": "Research queries",
            "ttl_days": rq_dismissed_ttl,
            "ttl_days_extra": {
                "approved": "forever",
                "pending": "forever",
                "dismissed": rq_dismissed_ttl,
                "error": rq_error_ttl,
            },
            "row_count": rq_total,
            "row_count_extra": {
                "pending": rq_pending,
                "approved": rq_approved,
                "dismissed": rq_dismissed,
                "error": rq_error,
            },
            "purge_endpoint": "/v1/admin/retention/research_queries/purge",
        },
    ]


# -----------------------------------------------------------------------------
# Single-tick orchestration (lifespan _retention_loop calls this).
# -----------------------------------------------------------------------------


async def run_full_sweep() -> dict:
    """Run all DB sweeps + vault sweeps + indexer reload. Best-effort.

    Returns a dict of per-sweep counts (or error strings).
    """
    counts: dict = {}
    counts["prediction_accuracy"] = await sweep_prediction_accuracy()
    counts["drift_alerts"] = await sweep_drift_alerts()
    counts["research_queries"] = await sweep_research_queries()

    # Auto-age stale pending research queries (30d default). Operator
    # asked us to dismiss rather than accumulate. Runs before the
    # rerank+rebalance so freshly-aged rows leave the pending pool first.
    try:
        from app.research import ranking as _ranking

        async with _db.SessionLocal() as session:
            counts["research_queries_auto_aged"] = await _ranking.auto_age_expired(
                session
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        counts["research_auto_age_error"] = str(e)

    # Nightly recompute of composite score + rebalance is_deferred for
    # the Today landing's top-5 panel.
    try:
        from app.research import ranking as _ranking

        async with _db.SessionLocal() as session:
            counts["research_queries_rescored"] = await _ranking.recompute_all_pending(
                session
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        counts["research_rescore_error"] = str(e)

    # Vault file sweeps — best-effort; module imports lazy so missing
    # vault doesn't break the loop.
    try:
        from tools.vault_indexer import cleanup_filings as _cleanup_filings

        counts["filings_8k_dropped"] = _cleanup_filings.cleanup_old_8k()
    except Exception as e:  # noqa: BLE001
        counts["filings_error"] = str(e)

    try:
        from tools.the_street import consolidate as _consolidate

        rolled_up = _consolidate.maybe_rollup_quarter()
        counts["the_street_quarter_rollup"] = rolled_up
    except Exception as e:  # noqa: BLE001
        counts["the_street_error"] = str(e)

    # Trigger indexer reload so freshly-deleted markdown disappears from
    # vault search results.
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8001/reload", timeout=5)
        counts["indexer_reload"] = "ok"
    except Exception as e:  # noqa: BLE001
        counts["indexer_reload"] = f"failed: {e}"

    return counts
