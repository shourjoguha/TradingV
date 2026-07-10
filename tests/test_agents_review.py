"""End-to-end tests for the reusable review CLI + report generator.

Exercised against the deterministic stub engine (DEBUG_STUB) on in-memory
SQLite — no network, no LLM, no watchlist membership required. Proves the batch
loop, the review augmentation + meta persistence, the JSON snapshot, and both
the markdown + HTML renderers, all offline.
"""
from __future__ import annotations

import datetime
import json

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.db as core_db
from app.core.config import SETTINGS
from app.core.db import Base

# Import model modules so create_all knows the tables under test.
from app.agents import models as _agents_models  # noqa: F401
from app.watchlist import models as _watchlist_models  # noqa: F401

from app.agents import review as agents_review
from scripts import agents_review as review_cli
from scripts import agents_report as report_gen


@pytest_asyncio.fixture
async def db():
    """In-memory SQLite bound to the app's SessionLocal for the test's duration."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    maker = async_sessionmaker(engine, expire_on_commit=False)
    prev_engine, prev_maker = core_db.engine, core_db.SessionLocal
    core_db.engine, core_db.SessionLocal = engine, maker
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield maker
    finally:
        core_db.engine, core_db.SessionLocal = prev_engine, prev_maker
        await engine.dispose()


@pytest.fixture
def debug_stub():
    prev = SETTINGS.DEBUG_STUB
    SETTINGS.DEBUG_STUB = True
    try:
        yield
    finally:
        SETTINGS.DEBUG_STUB = prev


def test_heuristic_review_shape():
    """Augmentation is deterministic + offline when the lane is disabled."""
    for stance, sign in (("BUY", 1), ("SELL", -1), ("HOLD", 0)):
        rev = agents_review.augment_decision(
            {"ticker": "TST", "stance": stance, "rationale_md": "line one\nline two"},
            allow_llm=False,
        )
        assert rev["source"] == "heuristic"
        assert rev["horizon"] == "6-12mo"
        assert rev["buy_level"] in agents_review.BUY_LEVELS
        assert rev["downside_pct"] <= 0 <= rev["upside_pct"]


def test_coerce_review_normalizes_bad_llm_output():
    raw = {"buy_level": "wildly-bullish", "downside_pct": "-12%", "upside_pct": 30,
           "key_risks": "single risk", "catalysts": ["a", "b", "c", "d"]}
    rev = agents_review._coerce_review(raw)
    assert rev["buy_level"] == "fair"          # unknown → fair
    assert rev["downside_pct"] == -12.0         # parsed, forced negative
    assert rev["upside_pct"] == 30.0
    assert rev["key_risks"] == ["single risk"]  # str → 1-elem list
    assert len(rev["catalysts"]) == 3           # capped at 3


@pytest.mark.asyncio
async def test_review_tickers_runs_and_persists(db, debug_stub):
    made_on = datetime.date(2026, 7, 10)
    snap = await review_cli.review_tickers(["msft", "googl", "mstr"], made_on=made_on)

    assert snap["stats"] == {"scanned": 3, "ok": 3, "failed": 0}
    tickers = {d["ticker"] for d in snap["decisions"]}
    assert tickers == {"MSFT", "GOOGL", "MSTR"}
    for d in snap["decisions"]:
        assert d["stance"] in {"BUY", "SELL", "HOLD"}
        assert d["review"]["horizon"] == "6-12mo"       # augmentation attached
        assert d["review"]["source"] == "heuristic"

    # Persistence: the review is on meta and readable back via the service.
    from app.agents import service as agents_service
    rows = await agents_service.list_decisions(ticker="MSFT", include_meta=True)
    assert rows[0]["review"]["horizon"] == "6-12mo"


@pytest.mark.asyncio
async def test_report_renders_md_and_html(db, debug_stub, tmp_path):
    made_on = datetime.date(2026, 7, 10)
    snap = await review_cli.review_tickers(["MSFT", "NFLX"], made_on=made_on)
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps(snap), encoding="utf-8")

    loaded = report_gen.load_from_json(snap_path)
    md = report_gen.render_markdown(loaded)
    htmldoc = report_gen.render_html(loaded)

    assert "# Agents-lane buy review" in md
    assert "MSFT" in md and "NFLX" in md
    assert "6–12mo" in md
    assert "stub" in md.lower()  # stub-preview warning present

    assert htmldoc.startswith("<!doctype html>")
    assert "Buy-level review" in htmldoc
    assert 'data-theme="dark"' in htmldoc  # theme-aware
    assert htmldoc.count("class=\"card\"") == 2


def test_report_cli_requires_output(tmp_path):
    snap = {"engine": "stub", "made_on": "2026-07-10", "decisions": []}
    p = tmp_path / "s.json"
    p.write_text(json.dumps(snap), encoding="utf-8")
    assert report_gen.main(["--from", str(p)]) == 2  # no --md/--html
