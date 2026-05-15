"""Static metadata for every laptop-side background loop.

This file is the single source of truth the Admin UI consults to render the
Processes + Cadences tabs. Every loop spawned in ``app.main:lifespan`` MUST
appear here. ``app.admin.runtime`` keeps the live handles (stop_event +
manual fire callable) populated at lifespan-startup time.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoopMeta:
    loop_id: str
    title: str
    description: str
    default_cadence_seconds: int
    supports_abort: bool
    confirm_modal_required: bool
    cost_sensitive: bool  # True if loop calls Anthropic / OpenAI / paid API
    default_enabled: bool


# Cadence units (humanized for the Cadences tab).
HOUR = 60 * 60
DAY = 24 * HOUR
WEEK = 7 * DAY


LOOPS: dict[str, LoopMeta] = {
    "accuracy": LoopMeta(
        loop_id="accuracy",
        title="Accuracy evaluator",
        description="Hourly: fills prediction_accuracy as predictions elapse.",
        default_cadence_seconds=HOUR,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "drift": LoopMeta(
        loop_id="drift",
        title="Drift detector",
        description="6-hourly: flags pairs where recent MAPE has degraded.",
        default_cadence_seconds=6 * HOUR,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "digest": LoopMeta(
        loop_id="digest",
        title="Daily Telegram digest",
        description="Daily roll-up sent at DIGEST_HOUR_UTC.",
        default_cadence_seconds=DAY,
        supports_abort=True,
        confirm_modal_required=True,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "macro": LoopMeta(
        loop_id="macro",
        title="Macro ingestion",
        description="Daily yfinance + FRED refresh of macro_series.",
        default_cadence_seconds=DAY,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "opps": LoopMeta(
        loop_id="opps",
        title="Opportunity generator",
        description="Hourly: rule engine over recent predictions.",
        default_cadence_seconds=HOUR,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "hyp_tick": LoopMeta(
        loop_id="hyp_tick",
        title="Hypothesis tick",
        description="Daily TTL expiry → invalidator eval → cascade.",
        default_cadence_seconds=DAY,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "research_weekly": LoopMeta(
        loop_id="research_weekly",
        title="Research weekly auto-stress",
        description=(
            "Pre-ranked stress-tests for at-risk hypotheses. Anthropic "
            "Sonnet calls. Default OFF; manual fire preferred."
        ),
        default_cadence_seconds=30 * DAY,  # monthly when enabled (cost-aware C1)
        supports_abort=True,
        confirm_modal_required=True,
        cost_sensitive=True,
        default_enabled=False,  # cost-aware C1
    ),
    "video_ingest": LoopMeta(
        loop_id="video_ingest",
        title="Video channel auto-ingest",
        description="Hourly poll of every Videos/<channel>/_channel.yaml.",
        default_cadence_seconds=HOUR,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=False,  # opt-in via VIDEO_INGEST_ENABLED
    ),
    "edgar_ingest": LoopMeta(
        loop_id="edgar_ingest",
        title="SEC EDGAR ingest",
        description="6-hourly: poll roster tickers for 8-K / 10-Q / 10-K.",
        default_cadence_seconds=6 * HOUR,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=False,  # opt-in via EDGAR_INGEST_ENABLED
    ),
    "tv_context_expire": LoopMeta(
        loop_id="tv_context_expire",
        title="TV Context expire-sweep",
        description="Hourly (laptop) / daily (Railway): drops expired payloads.",
        default_cadence_seconds=HOUR,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "outbox_purge": LoopMeta(
        loop_id="outbox_purge",
        title="Sync outbox purge",
        description="Periodic delete of completed sync_outbox rows.",
        default_cadence_seconds=HOUR,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "sync_drain": LoopMeta(
        loop_id="sync_drain",
        title="Sync outbox drain",
        description="5-min batch push of pending outbox rows to peer.",
        default_cadence_seconds=300,
        supports_abort=True,
        confirm_modal_required=True,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "queue_worker": LoopMeta(
        loop_id="queue_worker",
        title="Submit-queue worker",
        description="Single-flight FIFO drain of analysis submissions.",
        default_cadence_seconds=10,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "retention": LoopMeta(
        loop_id="retention",
        title="Retention sweep",
        description=(
            "Daily DB + vault retention sweep. Drops aged prediction_accuracy / "
            "drift_alerts / dismissed-or-error research_queries / 8-K filings; "
            "writes The Street quarterly rollup; reloads the vault indexer."
        ),
        default_cadence_seconds=DAY,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "ticker_review_digest": LoopMeta(
        loop_id="ticker_review_digest",
        title="Ticker review weekly digest",
        description=(
            "Daily tick — emits the Sunday markdown rollup to "
            "<vault>/Topics/_ticker-review-queue.md when weekday==Sun."
        ),
        default_cadence_seconds=DAY,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    "earnings_calendar": LoopMeta(
        loop_id="earnings_calendar",
        title="Earnings calendar refresh",
        description=(
            "Weekly full-universe refresh from yfinance + NASDAQ; per-ticker "
            "on-demand when ≤14d to release. Free providers, no API cost."
        ),
        default_cadence_seconds=DAY,
        supports_abort=True,
        confirm_modal_required=False,
        cost_sensitive=False,
        default_enabled=True,
    ),
    # Phase 5 will register `retention`.
}
