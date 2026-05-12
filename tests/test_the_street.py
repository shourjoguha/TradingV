"""Tests for /v1/the-street/* — read-only smart-money snapshot wrapper.

A tiny synthetic vault is built per-test under ``tmp_path`` and pointed at via
``tools.the_street.query.DEFAULT_VAULT`` (monkeypatched). The tests cover:
list snapshots, ticker history across snapshots, tier listing with ETF
exclusion, politician timeline, and the not-found / bad-tier paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.the_street import query as ts_query


HEADERS = {"X-API-Key": "test-key"}


# ---------------------------------------------------------------------------
# Fixture: minimal multi-snapshot vault
# ---------------------------------------------------------------------------

AGGREGATE_TSV = (
    "Ticker\tETF?\tBillionaires\tTrailblazers\tInsiders\tPoliticians\tOptions-Bullish\tChannels\tTotalSignals\tNotable\n"
    "META\t\t3\t7\t0\t1\t2\t4\t13\tBIL: tepper | TB: 7 funds | POL: Cleo Fields\n"
    "TSM\t\t2\t7\t3\t1\t0\t4\t13\tBIL: laffont | TB: 7 funds | POL: Cisneros\n"
    "MU\t\t1\t8\t0\t1\t1\t4\t11\tBIL: tepper | TB: 8 funds\n"
    "GOOGL\t\t2\t3\t0\t1\t1\t4\t7\tBIL: gayner | TB: 3 funds\n"
    "NVDA\t\t2\t12\t0\t0\t4\t3\t18\tBIL: laffont | TB: 12 funds\n"
    "MSFT\t\t1\t10\t0\t0\t1\t3\t12\tBIL: tepper | TB: 10 funds\n"
    "AMZN\t\t1\t13\t0\t0\t0\t2\t14\tBIL: laffont | TB: 13 funds\n"
    "SPY\tY\t0\t40\t0\t0\t0\t1\t40\tETF row — should be excluded by default\n"
)

POLITICIANS_TSV = (
    "2026-02-25\t2026-02-03\tGOOGL\tAlphabet\t40\t+32%\tCleo Fields\tREP\tLA06\t\t$100,001 - $250,000\n"
    "2026-02-25\t2026-02-03\tMETA\tMeta\t64\t+6%\tCleo Fields\tREP\tLA06\t\t$100,001 - $250,000\n"
    "2026-03-10\t2026-02-09\tTSM\tTSMC\t46\t-3%\tGilbert Cisneros\tREP\tCA31\t\t$100,001 - $250,000\n"
)


def _build_vault(root: Path, dates: list[str]) -> Path:
    street = root / "The Street"
    for d in dates:
        snap_dir = street / "snapshots" / d
        data_dir = street / "data" / d
        snap_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "_index.md").write_text(f"# Snapshot {d}\n", encoding="utf-8")
        (data_dir / "multi-channel-tickers.tsv").write_text(
            AGGREGATE_TSV, encoding="utf-8"
        )
        (data_dir / "politicians.tsv").write_text(
            POLITICIANS_TSV, encoding="utf-8"
        )
    return street


@pytest.fixture
def vault_with_two_snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _build_vault(tmp_path, ["2026-04-15", "2026-05-08"])
    monkeypatch.setattr(ts_query, "DEFAULT_VAULT", tmp_path)
    return tmp_path


@pytest.fixture
def empty_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ts_query, "DEFAULT_VAULT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_snapshots_returns_dates_sorted_descending(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/snapshots", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert [s["date"] for s in body["items"]] == ["2026-05-08", "2026-04-15"]
    # Vault path used for indexer node fetch is provided.
    assert body["items"][0]["vault_path"].endswith("/_index.md")


@pytest.mark.asyncio
async def test_list_snapshots_empty_vault_returns_zero(client, empty_vault: Path):
    r = await client.get("/v1/the-street/snapshots", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"items": [], "count": 0}


# ---------------------------------------------------------------------------
# Ticker history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ticker_history_aggregates_across_snapshots(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/ticker/META", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "META"
    assert body["count"] == 2
    assert {row["date"] for row in body["items"]} == {"2026-04-15", "2026-05-08"}
    assert body["items"][0]["channels"] == 4


@pytest.mark.asyncio
async def test_ticker_history_lowercase_input_normalises(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/ticker/meta", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["ticker"] == "META"
    assert r.json()["count"] == 2


@pytest.mark.asyncio
async def test_ticker_history_unknown_returns_empty(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/ticker/ZZZZ", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"ticker": "ZZZZ", "items": [], "count": 0}


# ---------------------------------------------------------------------------
# Tier listing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tier_one_default_excludes_etfs(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/tier/1", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_date"] == "2026-05-08"  # latest by default
    tickers = {row["ticker"] for row in body["items"]}
    assert tickers == {"META", "TSM", "MU", "GOOGL"}
    # ETF excluded by default.
    assert "SPY" not in tickers


@pytest.mark.asyncio
async def test_tier_two_returns_three_channel_names(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/tier/2", headers=HEADERS)
    assert r.status_code == 200
    tickers = {row["ticker"] for row in r.json()["items"]}
    assert tickers == {"NVDA", "MSFT"}


@pytest.mark.asyncio
async def test_tier_three_requires_trailblazers_cluster(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/tier/3", headers=HEADERS)
    assert r.status_code == 200
    # AMZN has 2 channels and 13 trailblazers (>=5) so it qualifies.
    tickers = {row["ticker"] for row in r.json()["items"]}
    assert tickers == {"AMZN"}


@pytest.mark.asyncio
async def test_tier_supports_explicit_date(
    client, vault_with_two_snapshots: Path
):
    r = await client.get(
        "/v1/the-street/tier/1?date=2026-04-15", headers=HEADERS
    )
    assert r.status_code == 200
    assert r.json()["snapshot_date"] == "2026-04-15"


@pytest.mark.asyncio
async def test_tier_unknown_date_returns_404(
    client, vault_with_two_snapshots: Path
):
    r = await client.get(
        "/v1/the-street/tier/1?date=2099-01-01", headers=HEADERS
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tier_invalid_value_returns_400(
    client, vault_with_two_snapshots: Path
):
    r = await client.get("/v1/the-street/tier/9", headers=HEADERS)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_tier_include_etfs_flag(
    client, vault_with_two_snapshots: Path
):
    r = await client.get(
        "/v1/the-street/tier/1?include_etfs=true", headers=HEADERS
    )
    assert r.status_code == 200
    tickers = {row["ticker"] for row in r.json()["items"]}
    # SPY has 1 channel so it's not Tier 1 even with ETFs included; this
    # only proves the flag is plumbed and doesn't crash.
    assert "META" in tickers


# ---------------------------------------------------------------------------
# Politician
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_politician_history_lists_disclosures(
    client, vault_with_two_snapshots: Path
):
    r = await client.get(
        "/v1/the-street/politician/Cleo Fields", headers=HEADERS
    )
    assert r.status_code == 200
    body = r.json()
    # Two tickers in the row × two snapshots.
    assert body["count"] == 4
    tickers = {row["ticker"] for row in body["items"]}
    assert tickers == {"GOOGL", "META"}


@pytest.mark.asyncio
async def test_politician_history_unknown_returns_empty(
    client, vault_with_two_snapshots: Path
):
    r = await client.get(
        "/v1/the-street/politician/Nobody", headers=HEADERS
    )
    assert r.status_code == 200
    assert r.json() == {"politician": "Nobody", "items": [], "count": 0}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_required(client, vault_with_two_snapshots: Path):
    r = await client.get("/v1/the-street/snapshots")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Per-ticker digest (accordion content)
# ---------------------------------------------------------------------------

INSIDERS_TSV = (
    "2026-05-07\tMETA\tMeta Platforms\t40\tJane Doe\tDirector\t$100k\t1k\t$610.00\t+\n"
)

TRAILBLAZERS_JSON = (
    '{"Some Fund": ["META\\tMeta Platforms\\t\\u25b2 Added", '
    '"NVDA\\tNVIDIA\\tNew"]}'
)


def _add_raw_files(date_dir: Path) -> None:
    (date_dir / "insiders.tsv").write_text(INSIDERS_TSV, encoding="utf-8")
    (date_dir / "trailblazers.json").write_text(TRAILBLAZERS_JSON, encoding="utf-8")


@pytest.mark.asyncio
async def test_digest_lazy_builds_when_missing(
    client, vault_with_two_snapshots: Path
):
    # Add raw files for one snapshot (politicians.tsv already there) so the
    # builder has something to read.
    snap_data = vault_with_two_snapshots / "The Street" / "data" / "2026-05-08"
    _add_raw_files(snap_data)
    # Confirm digests.json absent on entry.
    digest_path = snap_data / "digests.json"
    if digest_path.exists():
        digest_path.unlink()

    r = await client.get(
        "/v1/the-street/digest/2026-05-08/META", headers=HEADERS
    )
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["ticker"] == "META"
    assert body["entry"]["channels"]["politicians"][0]["member"] == "Cleo Fields"
    # Builder created the file.
    assert digest_path.exists()


@pytest.mark.asyncio
async def test_digest_unknown_ticker_returns_not_found_flag(
    client, vault_with_two_snapshots: Path
):
    r = await client.get(
        "/v1/the-street/digest/2026-05-08/ZZZZ", headers=HEADERS
    )
    assert r.status_code == 200
    assert r.json()["found"] is False
    assert r.json()["entry"] is None


@pytest.mark.asyncio
async def test_digest_unknown_snapshot_date_returns_404(
    client, vault_with_two_snapshots: Path
):
    r = await client.get(
        "/v1/the-street/digest/2099-01-01/META", headers=HEADERS
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_digest_markdown_includes_copy_friendly_block(
    client, vault_with_two_snapshots: Path
):
    snap_data = vault_with_two_snapshots / "The Street" / "data" / "2026-05-08"
    _add_raw_files(snap_data)
    r = await client.get(
        "/v1/the-street/digest/2026-05-08/META", headers=HEADERS
    )
    md = r.json()["entry"]["markdown"]
    assert "# META" in md
    assert "Politicians" in md
    assert "Cleo Fields" in md
