import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import SETTINGS
from app.core.db import engine

# Ensure models are imported so Base.metadata knows about them.
from app.alerts import models as _alert_models  # noqa: F401
from app.tickers import models as _ticker_models  # noqa: F401
from app.market_data import models as _ohlcv_models  # noqa: F401
from app.analysis import models as _analysis_models  # noqa: F401
from app.sync import models as _sync_models  # noqa: F401
from app.labels import models as _labels_models  # noqa: F401
from app.predictions import models as _predictions_models  # noqa: F401
from app.schedule import models as _schedule_models  # noqa: F401
from app.watchlist import models as _watchlist_models  # noqa: F401
from app.accuracy import models as _accuracy_models  # noqa: F401
from app.opportunities import models as _opportunities_models  # noqa: F401
from app.trades import models as _trades_models  # noqa: F401
from app.market_data import derived as _derived_models  # noqa: F401
from app.queue import models as _queue_models  # noqa: F401
from app.hypotheses import models as _hypothesis_models  # noqa: F401
from app.research import models as _research_models  # noqa: F401
# Macro models are already imported via app.macro.* downstream; explicit
# import here for create_all parity with the test conftest.
from app.macro import models as _macro_models  # noqa: F401
from app.boards import models as _board_models  # noqa: F401
from app.tv_context import models as _tv_context_models  # noqa: F401
from app.admin import models as _admin_models  # noqa: F401
from app.earnings import models as _earnings_models  # noqa: F401
from app.ticker_review import models as _ticker_review_models  # noqa: F401
from app.rx import models as _rx_models  # noqa: F401
from app.content import models as _content_models  # noqa: F401
from app.agents import models as _agents_models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        # Schema is migration-driven. We do NOT call Base.metadata.create_all
        # here anymore — it raced ahead of `alembic upgrade head` twice in
        # 24h (M-2 on 2026-05-01 + Phase 2 on 2026-05-02), blocking the
        # actual migration with "relation already exists" errors and
        # masking subtler drift (a column added in a migration would not
        # be created by create_all, but tables would look fine).
        # See ADR-013/014 + the backlog entry resolved 2026-05-02.
        # Tests build their schema from models in tests/conftest.py — the
        # only place create_all should run.
        from app.core.schema_check import warn_if_drift

        await warn_if_drift(engine)

        # Parse the markdown view registry once at boot. Errors fail the
        # boot loudly so the operator sees the broken file immediately.
        from app.views import parser as _views_parser

        _views_parser.reload()

        from app.core.config import SETTINGS

        if SETTINGS.KRONOS_ENABLED:
            from app.kronos.real_adapter import activate as activate_kronos

            activate_kronos()

        # Agents lane (TradingAgents) — swap the stub engine for the real one.
        # Side-by-side with Kronos; ships dark unless AGENTS_ENABLED.
        if SETTINGS.AGENTS_ENABLED:
            from app.agents.real_engine import activate as activate_agents

            activate_agents()

        import asyncio

        # Tests set DISABLE_LIFESPAN_BACKGROUND_TASKS=1 in conftest. Skipping
        # the spawn block entirely guarantees pytest fixtures tear down
        # cleanly — no orphan tasks, no warmup waits colliding with
        # assertions, no test runs that need to be killed externally.
        # Production unchanged — the env var is unset there.
        if os.environ.get("DISABLE_LIFESPAN_BACKGROUND_TASKS"):
            logger.info("lifespan: background tasks disabled by env flag")
            yield
            return

        # rx config visibility — surface the operator UUID + ingest-token
        # state at boot so a misconfigured deploy is immediately visible
        # in the log. UUID is not sensitive (just identifies the operator
        # in single-tenant Lovable). Token state is reported as
        # configured/unset only — never the value.
        logger.info(
            "rx config: RX_OPERATOR_UUID=%s, ingest=%s",
            SETTINGS.RX_OPERATOR_UUID,
            "configured" if SETTINGS.RX_INGEST_TOKEN else "DISABLED",
        )

        # Best-effort drain of outbox rows left pending from prior process.

        from app.sync import service as _sync_service

        # Railway is a passive replica — it never enqueues outbound rows
        # (origin='peer' on imported jobs bypasses enqueue), so its
        # outbox is empty. Skip the catch-up drain on Railway to avoid a
        # gratuitous wake of the peer.
        is_railway = SETTINGS.INSTANCE_NAME == "railway"

        if (
            not is_railway
            and SETTINGS.SYNC_ENABLED
            and _sync_service.peer_configured()
        ):
            asyncio.create_task(_sync_service.drain_outbox())

        # Periodic outbox purge — keeps completed rows from growing
        # unbounded. Useful on both sides (Railway also accumulates rows
        # if the operator ever points TWO laptops at one Railway).
        purge_task = asyncio.create_task(_sync_service.purge_loop(), name="outbox-purge")

        # Periodic outbox drain — laptop-only. Replaces the previous
        # per-analysis-job `asyncio.create_task(drain_outbox)` pattern so
        # we batch sync pushes instead of waking Railway on every job
        # completion. Railway pays per active minute; serverless cost
        # tracks wake-up count.
        sync_drain_task = None
        sync_drain_stop = asyncio.Event()
        if (
            not is_railway
            and SETTINGS.SYNC_ENABLED
            and _sync_service.peer_configured()
        ):
            async def _sync_drain_loop() -> None:
                interval = SETTINGS.SYNC_DRAIN_INTERVAL_SECONDS
                while True:
                    try:
                        await asyncio.wait_for(sync_drain_stop.wait(), timeout=interval)
                        if sync_drain_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        pass
                    try:
                        await _sync_service.drain_outbox()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.warning("sync drain tick failed: %s", e)

            sync_drain_task = asyncio.create_task(_sync_drain_loop(), name="sync-drain")

        # Daily forecast scheduler (idle until enabled via PUT /v1/schedule).
        from app.schedule import runner as _schedule_runner

        _schedule_runner.start()

        # ---- Loops below: LAPTOP ONLY -----------------------------------
        # Railway is a passive replica + read API + webhook receiver. None
        # of these loops produce data Railway needs to compute itself —
        # all writes flow laptop → Railway via the outbox. Running them on
        # Railway only burns serverless wake-ups + risks duplicate
        # Telegram alerts / yfinance hits / hypothesis ticks.
        accuracy_task = None
        drift_task = None
        digest_task = None
        market_data_task = None
        opps_task = None
        agents_task = None
        macro_task = None
        hyp_task = None
        research_task = None
        video_ingest_task = None
        edgar_ingest_task = None
        queue_task = None
        earnings_calendar_task = None
        earnings_calendar_stop = asyncio.Event()
        retention_task = None
        retention_stop = asyncio.Event()
        ticker_review_digest_task = None
        ticker_review_digest_stop = asyncio.Event()
        accuracy_stop = asyncio.Event()
        drift_stop = asyncio.Event()
        digest_stop = asyncio.Event()
        market_data_stop = asyncio.Event()
        opps_stop = asyncio.Event()
        agents_stop = asyncio.Event()
        macro_stop = asyncio.Event()
        hyp_stop = asyncio.Event()
        research_stop = asyncio.Event()
        video_ingest_stop = asyncio.Event()
        edgar_ingest_stop = asyncio.Event()
        queue_stop = asyncio.Event()

        # tv_context expire-sweep runs on BOTH sides (Railway has its own
        # imported tv_context_items rows that need expiring) but at
        # different cadence — laptop hourly, Railway daily — to minimise
        # serverless wake-ups.
        from app.tv_context import service as _tvc_service

        tv_context_stop = asyncio.Event()
        tv_context_interval = (
            SETTINGS.TV_CTX_EXPIRE_INTERVAL_SECONDS
            if not is_railway
            else max(SETTINGS.TV_CTX_EXPIRE_INTERVAL_SECONDS, 86400)
        )
        tv_context_task = asyncio.create_task(
            _tvc_service.expire_loop(
                stop_event=tv_context_stop, interval_seconds=tv_context_interval
            ),
            name="tv-context-expire",
        )

        if is_railway:
            logger.info(
                "lifespan: skipping laptop-only loops (INSTANCE_NAME=railway)"
            )
        else:
            # Hourly accuracy evaluator — fills prediction_accuracy as predictions
            # elapse and actuals land in ohlcv_bars. Idempotent; safe to interrupt.
            from app.accuracy import drift as _drift, service as _accuracy_service

            accuracy_task = asyncio.create_task(
                _accuracy_service.evaluator_loop(stop_event=accuracy_stop),
                name="accuracy-evaluator",
            )

            # 6-hourly drift detector — flags pairs whose recent MAPE has
            # degraded past DRIFT_RATIO_THRESHOLD vs all-time. Posts to
            # Telegram if configured.
            drift_task = asyncio.create_task(
                _drift.detector_loop(stop_event=drift_stop),
                name="drift-detector",
            )

            # Daily Telegram digest at DIGEST_HOUR_UTC.
            from app.notifications import digest as _digest

            digest_task = asyncio.create_task(
                _digest.digest_loop(stop_event=digest_stop),
                name="daily-digest",
            )

            # Daily market-data refresh — IV percentile + earnings dates per
            # watchlist ticker. Phase 6 options runway. Best-effort; failures
            # logged + skipped.
            from app.market_data import derived as _derived

            market_data_task = asyncio.create_task(
                _derived.market_data_loop(stop_event=market_data_stop),
                name="market-data-derived",
            )

            # Hourly opportunity generator — runs rule engine over recent
            # predictions, sweeps expired open opportunities. Phase 3.1.
            from app.opportunities import service as _opps_service

            async def _opps_loop() -> None:
                while True:
                    try:
                        await _opps_service.generate_for_predictions()
                        await _opps_service.expire_stale()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.warning("opportunities tick failed: %s", e)
                    try:
                        # Daily — opps rule engine over predictions; runs once
                        # per day after accuracy + drift have new actuals.
                        # Reduced 2026-05-16 from hourly per operator request.
                        await asyncio.wait_for(opps_stop.wait(), timeout=24 * 60 * 60)
                        if opps_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        continue

            opps_task = asyncio.create_task(_opps_loop(), name="opportunities-tick")

            # Daily Agents-lane decisions — TradingAgents multi-agent engine
            # over the watchlist roster. Side-by-side with Kronos; gated by
            # AGENTS_ENABLED (default off, so this never runs unless the
            # operator opts in + installs requirements-agents.txt). Warmup
            # defers the first tick so it doesn't collide with the opps/macro
            # ticks at boot.
            if SETTINGS.AGENTS_ENABLED:
                from app.agents import service as _agents_service

                async def _agents_loop() -> None:
                    interval = SETTINGS.AGENTS_SLEEP_SECONDS
                    warmup = SETTINGS.AGENTS_WARMUP_SECONDS
                    try:
                        await asyncio.wait_for(agents_stop.wait(), timeout=warmup)
                        if agents_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        pass
                    while True:
                        try:
                            stats = await _agents_service.run_for_watchlist()
                            logger.info("agents tick: %s", stats)
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:  # noqa: BLE001
                            logger.warning("agents tick failed: %s", e)
                        try:
                            await asyncio.wait_for(agents_stop.wait(), timeout=interval)
                            if agents_stop.is_set():
                                return
                        except asyncio.TimeoutError:
                            continue

                agents_task = asyncio.create_task(_agents_loop(), name="agents-tick")

            # Daily macro signal-layer ingestion — yfinance + FRED. Phase M-1
            # of the Macro Workbench. Idempotent upserts; first tick fires
            # immediately for catch-up, then daily.
            from app.macro import service as _macro_service

            macro_task = asyncio.create_task(
                _macro_service.ingestion_loop(stop_event=macro_stop),
                name="macro-ingestion",
            )

            # Daily hypothesis tick — TTL expiry → invalidator eval → cascade.
            # M-2. Runs every 24h; first tick deferred 5 minutes after boot to
            # let macro ingestion get a head start on day 0.
            from app.hypotheses import service as _hyp_service

            async def _hyp_loop() -> None:
                try:
                    await asyncio.wait_for(hyp_stop.wait(), timeout=5 * 60)
                    if hyp_stop.is_set():
                        return
                except asyncio.TimeoutError:
                    pass
                while True:
                    try:
                        async with _db_pkg.SessionLocal() as session:
                            stats = await _hyp_service.run_daily_tick(session)
                            await session.commit()
                        logger.info("hypothesis tick: %s", stats)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.warning("hypothesis tick failed: %s", e)
                    try:
                        await asyncio.wait_for(hyp_stop.wait(), timeout=24 * 60 * 60)
                        if hyp_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        continue

            from app.core import db as _db_pkg

            hyp_task = asyncio.create_task(_hyp_loop(), name="hypothesis-tick")

            # Phase 3 weekly auto-stress — fires once per active hypothesis per
            # week. Off when ANTHROPIC_API_KEY is missing (inner loop logs + skips).
            from app.research import weekly as _research_weekly

            research_task = asyncio.create_task(
                _research_weekly.loop(research_stop),
                name="research-weekly",
            )

            # Video channel auto-ingest — hourly poll of every
            # `Videos/<channel>/_channel.yaml` whose cadence has elapsed.
            # Off by default (VIDEO_INGEST_ENABLED=false) so existing operators
            # opt in deliberately. Per-channel failures logged + skipped.
            if SETTINGS.VIDEO_INGEST_ENABLED:
                async def _video_ingest_loop() -> None:
                    from tools.vault_indexer.ingest import youtube_channel as _yt
                    interval = SETTINGS.VIDEO_INGEST_SLEEP_SECONDS
                    warmup = SETTINGS.VIDEO_INGEST_WARMUP_SECONDS
                    try:
                        await asyncio.wait_for(video_ingest_stop.wait(), timeout=warmup)
                        if video_ingest_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        pass
                    while True:
                        try:
                            # Pass current earnings dates so IR channels with
                            # earnings_trigger blocks only poll on release days.
                            from app.earnings import service as _earnings_svc

                            try:
                                upcoming = await _earnings_svc.upcoming_earnings(days=60)
                                import datetime as _dt
                                earnings_dates = {
                                    item["ticker"]: (
                                        _dt.date.fromisoformat(item["expected_at"])
                                        if item.get("expected_at")
                                        else None
                                    )
                                    for item in upcoming
                                }
                            except Exception:  # noqa: BLE001
                                earnings_dates = {}
                            results = await asyncio.to_thread(
                                _yt.ingest_all, earnings_dates=earnings_dates
                            )
                            drafts = sum((r.get("drafts_written") or 0) for r in results)
                            if drafts:
                                logger.info("video-ingest: %d new draft(s) across %d channels", drafts, len(results))
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:                # noqa: BLE001
                            logger.warning("video-ingest tick failed: %s", e)
                        try:
                            await asyncio.wait_for(video_ingest_stop.wait(), timeout=interval)
                            if video_ingest_stop.is_set():
                                return
                        except asyncio.TimeoutError:
                            continue

                video_ingest_task = asyncio.create_task(
                    _video_ingest_loop(), name="video-ingest"
                )

            # SEC EDGAR auto-ingest — poll every operational-watchlist
            # ticker for new 8-K / 10-Q / 10-K filings. Idempotent on
            # accession_number. Off by default (EDGAR_INGEST_ENABLED=false);
            # opt in after setting EDGAR_USER_AGENT.
            if SETTINGS.EDGAR_INGEST_ENABLED:
                async def _edgar_ingest_loop() -> None:
                    from sqlalchemy import select

                    from app.core import db as _db_local
                    from app.watchlist.models import WatchlistEntry
                    from tools.vault_indexer.ingest import ingest_edgar as _edgar

                    interval = SETTINGS.EDGAR_INGEST_SLEEP_SECONDS
                    warmup = SETTINGS.EDGAR_INGEST_WARMUP_SECONDS
                    form_types = [
                        f.strip()
                        for f in (SETTINGS.EDGAR_INGEST_FORM_TYPES or "").split(",")
                        if f.strip()
                    ]
                    max_per_form = SETTINGS.EDGAR_INGEST_MAX_PER_FORM
                    try:
                        await asyncio.wait_for(
                            edgar_ingest_stop.wait(), timeout=warmup
                        )
                        if edgar_ingest_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        pass
                    while True:
                        try:
                            async with _db_local.SessionLocal() as session:
                                rows = await session.execute(
                                    select(WatchlistEntry.symbol).order_by(
                                        WatchlistEntry.symbol
                                    )
                                )
                                tickers = [r[0] for r in rows]
                            if tickers:
                                results = await asyncio.to_thread(
                                    _edgar.ingest_tickers,
                                    tickers,
                                    form_types=form_types,
                                    max_per_form=max_per_form,
                                )
                                written = sum(
                                    (r.get("written") or 0) for r in results
                                )
                                if written:
                                    logger.info(
                                        "edgar-ingest: %d new filing(s) across %d tickers",
                                        written, len(tickers),
                                    )
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:                # noqa: BLE001
                            logger.warning("edgar-ingest tick failed: %s", e)
                        try:
                            await asyncio.wait_for(
                                edgar_ingest_stop.wait(), timeout=interval
                            )
                            if edgar_ingest_stop.is_set():
                                return
                        except asyncio.TimeoutError:
                            continue

                edgar_ingest_task = asyncio.create_task(
                    _edgar_ingest_loop(), name="edgar-ingest"
                )

            # Submit-queue worker — single-flight FIFO drain. Boot recovery
            # first: any 'running' rows from a crashed prior process flip back
            # to 'pending' so this worker re-picks them.
            from app.queue import service as _qsvc, worker as _qworker

            n_recovered = await _qsvc.reset_stuck_on_boot()
            if n_recovered:
                logger.info("queue: recovered %d stuck rows on boot", n_recovered)

            queue_task = asyncio.create_task(
                _qworker.worker_loop(stop_event=queue_stop),
                name="queue-worker",
            )

            # Earnings calendar — daily refresh of the rolling universe.
            # Free providers; tiered cadence handled inside refresh_all.
            from app.earnings import service as _earnings_svc

            async def _earnings_calendar_loop() -> None:
                # Warmup so first tick doesn't collide with macro/research.
                try:
                    await asyncio.wait_for(
                        earnings_calendar_stop.wait(), timeout=2 * 60
                    )
                    if earnings_calendar_stop.is_set():
                        return
                except asyncio.TimeoutError:
                    pass
                while True:
                    try:
                        from app.admin import lifespan as _admin_lifespan2

                        async with _admin_lifespan2.tick_status("earnings_calendar"):
                            await _earnings_svc.refresh_all()
                            await _earnings_svc.purge_stale_universe()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.warning("earnings_calendar tick failed: %s", e)
                    try:
                        await asyncio.wait_for(
                            earnings_calendar_stop.wait(), timeout=24 * 60 * 60
                        )
                        if earnings_calendar_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        continue

            earnings_calendar_task = asyncio.create_task(
                _earnings_calendar_loop(), name="earnings-calendar"
            )

            # Retention sweep — daily. DB → vault files → indexer reload.
            from app.admin import retention as _retention

            async def _retention_loop() -> None:
                # Warmup so first sweep doesn't collide with macro/research.
                try:
                    await asyncio.wait_for(retention_stop.wait(), timeout=10 * 60)
                    if retention_stop.is_set():
                        return
                except asyncio.TimeoutError:
                    pass
                while True:
                    try:
                        from app.admin import lifespan as _admin_lifespan3

                        async with _admin_lifespan3.tick_status("retention"):
                            await _retention.run_full_sweep()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.warning("retention tick failed: %s", e)
                    try:
                        await asyncio.wait_for(
                            retention_stop.wait(), timeout=24 * 60 * 60
                        )
                        if retention_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        continue

            retention_task = asyncio.create_task(_retention_loop(), name="retention")

            # Ticker review weekly digest — daily tick, only emits the
            # Sunday markdown rollup. DB is canonical; markdown is a
            # derived snapshot for Obsidian search.
            import os as _os
            from pathlib import Path as _Path
            from zoneinfo import ZoneInfo as _ZoneInfo
            from app.ticker_review import service as _tr_svc_loop

            _vault_path = _os.environ.get(
                "VAULT_PATH",
                str(_Path.home() / "Documents" / "knowledge-vault"),
            )
            _NY_TZ_LOOP = _ZoneInfo("America/New_York")

            async def _ticker_review_digest_loop() -> None:
                # Warmup so first tick doesn't collide with retention.
                try:
                    await asyncio.wait_for(
                        ticker_review_digest_stop.wait(), timeout=15 * 60
                    )
                    if ticker_review_digest_stop.is_set():
                        return
                except asyncio.TimeoutError:
                    pass
                while True:
                    try:
                        from app.admin import lifespan as _admin_lifespan4
                        import datetime as _dt_loop
                        now_ny = _dt_loop.datetime.now(_NY_TZ_LOOP)
                        if now_ny.weekday() == 6:  # Sunday
                            async with _admin_lifespan4.tick_status(
                                "ticker_review_digest"
                            ):
                                path = await _tr_svc_loop.write_weekly_digest(
                                    _vault_path
                                )
                                if path:
                                    logger.info(
                                        "ticker-review digest written: %s", path
                                    )
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "ticker_review_digest tick failed: %s", e
                        )
                    try:
                        await asyncio.wait_for(
                            ticker_review_digest_stop.wait(),
                            timeout=24 * 60 * 60,
                        )
                        if ticker_review_digest_stop.is_set():
                            return
                    except asyncio.TimeoutError:
                        continue

            ticker_review_digest_task = asyncio.create_task(
                _ticker_review_digest_loop(), name="ticker-review-digest"
            )

        # ---- Admin runtime registration --------------------------------
        # Registers a live handle per loop so /v1/admin/loops/{id}/{fire,abort}
        # can find them. Manual fire callables call the underlying single-tick
        # function directly; abort sets the stop_event + cancels the task.
        from app.admin import lifespan as _admin_lifespan

        async def _no_fire() -> None:
            return None

        # Always-on handles (both laptop + Railway).
        _admin_lifespan.register_handle(
            "tv_context_expire", stop_event=tv_context_stop, task=tv_context_task
        )
        _admin_lifespan.register_handle(
            "outbox_purge", stop_event=None, task=purge_task
        )
        if sync_drain_task is not None:
            _admin_lifespan.register_handle(
                "sync_drain", stop_event=sync_drain_stop, task=sync_drain_task
            )

        if not is_railway:
            from app.accuracy import service as _acc_svc, drift as _drift_svc
            from app.notifications import digest as _digest_svc
            from app.market_data import derived as _md_derived
            from app.opportunities import service as _opps_svc
            from app.macro import service as _macro_svc
            from app.hypotheses import service as _hyp_svc
            from app.core import db as _db_pkg2

            async def _fire_macro() -> None:
                async with _admin_lifespan.tick_status("macro"):
                    await _macro_svc.refresh_all()

            async def _fire_opps() -> None:
                async with _admin_lifespan.tick_status("opps"):
                    await _opps_svc.generate_for_predictions()
                    await _opps_svc.expire_stale()

            async def _fire_hyp() -> None:
                async with _admin_lifespan.tick_status("hyp_tick"):
                    async with _db_pkg2.SessionLocal() as session:
                        await _hyp_svc.run_daily_tick(session)
                        await session.commit()

            async def _fire_accuracy() -> None:
                async with _admin_lifespan.tick_status("accuracy"):
                    if hasattr(_acc_svc, "evaluate_pending"):
                        await _acc_svc.evaluate_pending()

            async def _fire_drift() -> None:
                async with _admin_lifespan.tick_status("drift"):
                    if hasattr(_drift_svc, "detect_once"):
                        await _drift_svc.detect_once()

            async def _fire_digest() -> None:
                async with _admin_lifespan.tick_status("digest"):
                    if hasattr(_digest_svc, "send_digest_once"):
                        await _digest_svc.send_digest_once()

            async def _fire_market_data() -> None:
                async with _admin_lifespan.tick_status("market_data"):
                    if hasattr(_md_derived, "refresh_market_data_once"):
                        await _md_derived.refresh_market_data_once()

            _admin_lifespan.register_handle(
                "accuracy", stop_event=accuracy_stop, task=accuracy_task,
                fire_now=_fire_accuracy,
            )
            _admin_lifespan.register_handle(
                "drift", stop_event=drift_stop, task=drift_task,
                fire_now=_fire_drift,
            )
            _admin_lifespan.register_handle(
                "digest", stop_event=digest_stop, task=digest_task,
                fire_now=_fire_digest,
            )
            _admin_lifespan.register_handle(
                "macro", stop_event=macro_stop, task=macro_task,
                fire_now=_fire_macro,
            )
            _admin_lifespan.register_handle(
                "opps", stop_event=opps_stop, task=opps_task,
                fire_now=_fire_opps,
            )
            from app.agents import service as _agents_svc

            async def _fire_agents() -> None:
                async with _admin_lifespan.tick_status("agents"):
                    await _agents_svc.run_for_watchlist()

            _admin_lifespan.register_handle(
                "agents", stop_event=agents_stop, task=agents_task,
                fire_now=_fire_agents, enabled=SETTINGS.AGENTS_ENABLED,
            )
            _admin_lifespan.register_handle(
                "hyp_tick", stop_event=hyp_stop, task=hyp_task,
                fire_now=_fire_hyp,
            )
            from app.research import weekly as _research_weekly2

            async def _fire_research_weekly() -> None:
                async with _admin_lifespan.tick_status("research_weekly"):
                    # force=True bypasses the enabled gate (manual fire is
                    # the operator's explicit opt-in) but keeps scope/dedupe.
                    await _research_weekly2.run_once(force=True)

            _admin_lifespan.register_handle(
                "research_weekly",
                stop_event=research_stop,
                task=research_task,
                fire_now=_fire_research_weekly,
            )
            _admin_lifespan.register_handle(
                "video_ingest", stop_event=video_ingest_stop, task=video_ingest_task,
                enabled=SETTINGS.VIDEO_INGEST_ENABLED,
            )
            _admin_lifespan.register_handle(
                "edgar_ingest", stop_event=edgar_ingest_stop, task=edgar_ingest_task,
                enabled=SETTINGS.EDGAR_INGEST_ENABLED,
            )
            _admin_lifespan.register_handle(
                "queue_worker", stop_event=queue_stop, task=queue_task,
            )

            from app.earnings import service as _earnings_svc2

            async def _fire_earnings_calendar() -> None:
                async with _admin_lifespan.tick_status("earnings_calendar"):
                    await _earnings_svc2.refresh_all(force=True)
                    await _earnings_svc2.purge_stale_universe()

            _admin_lifespan.register_handle(
                "earnings_calendar",
                stop_event=earnings_calendar_stop,
                task=earnings_calendar_task,
                fire_now=_fire_earnings_calendar,
            )

            from app.admin import retention as _retention2

            async def _fire_retention() -> None:
                async with _admin_lifespan.tick_status("retention"):
                    await _retention2.run_full_sweep()

            _admin_lifespan.register_handle(
                "retention",
                stop_event=retention_stop,
                task=retention_task,
                fire_now=_fire_retention,
            )

            from app.ticker_review import service as _tr_svc_admin

            async def _fire_ticker_review_digest() -> None:
                async with _admin_lifespan.tick_status("ticker_review_digest"):
                    import os as _os_fire
                    from pathlib import Path as _Path_fire
                    vp = _os_fire.environ.get(
                        "VAULT_PATH",
                        str(_Path_fire.home() / "Documents" / "knowledge-vault"),
                    )
                    await _tr_svc_admin.write_weekly_digest(vp)

            _admin_lifespan.register_handle(
                "ticker_review_digest",
                stop_event=ticker_review_digest_stop,
                task=ticker_review_digest_task,
                fire_now=_fire_ticker_review_digest,
            )

        # Drift check: warn if any registered handle is missing from the
        # static loops registry. Doesn't block startup; surfaces in logs.
        drift = await _admin_lifespan.assert_registry_drift()
        if drift:
            logger.warning("admin loops drift: unregistered handles: %s", drift)

        yield

        # Clean shutdown. Some tasks are None on Railway (gated above) —
        # guard each cancel.
        await _schedule_runner.stop()
        purge_task.cancel()
        if sync_drain_task is not None:
            sync_drain_stop.set()
            sync_drain_task.cancel()
        for stop_evt, task in (
            (accuracy_stop, accuracy_task),
            (drift_stop, drift_task),
            (digest_stop, digest_task),
            (market_data_stop, market_data_task),
            (opps_stop, opps_task),
            (agents_stop, agents_task),
            (queue_stop, queue_task),
            (macro_stop, macro_task),
            (hyp_stop, hyp_task),
            (research_stop, research_task),
            (video_ingest_stop, video_ingest_task),
            (edgar_ingest_stop, edgar_ingest_task),
            (earnings_calendar_stop, earnings_calendar_task),
            (retention_stop, retention_task),
            (ticker_review_digest_stop, ticker_review_digest_task),
        ):
            stop_evt.set()
            if task is not None:
                task.cancel()
        tv_context_stop.set()
        tv_context_task.cancel()

    except Exception as e:
        logger.error("startup error: %s", e)
        raise


app = FastAPI(lifespan=lifespan, title="TradingView Analysis Platform")


def _cors_origins() -> list[str]:
    """Allow-list for the browser-side frontend.

    Production: set ``FRONTEND_ORIGIN`` to one or more comma-separated
    absolute origins (the deployed Lovable / Vercel URLs).

    Local dev: when ``FRONTEND_ORIGIN`` is empty we fall back to the
    common Vite (5173) and Next.js (3000) ports so a developer on the
    laptop can hit the API from a browser without env config.
    """
    raw = (SETTINGS.FRONTEND_ORIGIN or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
