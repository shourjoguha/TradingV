"""Tests for tools.vault_indexer.ingest.vignette_updater — sentinel-bounded upsert."""
from __future__ import annotations

from pathlib import Path

from tools.vault_indexer.ingest import vignette_updater as vu


# ---------------------------------------------------------------------------
# summarise_chart_references — one-line summary aggregator
# ---------------------------------------------------------------------------


def test_summarise_empty_input() -> None:
    assert vu.summarise_chart_references([]) == ""


def test_summarise_single_ref() -> None:
    out = vu.summarise_chart_references([
        {"chart_type": "candlestick", "timeframe": "4h", "tickers": ["BTC"]},
    ])
    assert "BTC" in out
    assert "candlestick" in out
    assert "4h" in out


def test_summarise_dedupes() -> None:
    refs = [
        {"chart_type": "candlestick", "timeframe": "1d", "tickers": ["BTC"]},
        {"chart_type": "candlestick", "timeframe": "1d", "tickers": ["BTC"]},
        {"chart_type": "line", "timeframe": "1w", "tickers": ["NASDAQ"]},
    ]
    out = vu.summarise_chart_references(refs)
    # BTC appears once; NASDAQ once.
    assert out.count("BTC") == 1
    assert "NASDAQ" in out


def test_summarise_falls_back_when_fields_missing() -> None:
    refs = [
        {"chart_type": "gauge"},
        {"chart_type": None, "timeframe": "1d"},
    ]
    out = vu.summarise_chart_references(refs)
    assert "gauge" in out
    assert "1d" in out


# ---------------------------------------------------------------------------
# render_block — sentinel markers + table
# ---------------------------------------------------------------------------


def test_render_block_empty_entries_has_placeholder() -> None:
    md = vu.render_block([])
    assert vu.SENTINEL_START in md
    assert vu.SENTINEL_END in md
    assert "No chart references captured yet" in md


def test_render_block_with_entries() -> None:
    md = vu.render_block([
        {
            "video_id": "abc",
            "published_at": "2026-05-14",
            "title": "Test Video",
            "rel_path": "Videos/test/2026-W19.md",
            "summary": "BTC (4h candlestick)",
        },
    ])
    assert vu.SENTINEL_START in md
    assert "2026-05-14" in md
    assert "[Test Video]" in md  # markdown link
    assert "BTC (4h candlestick)" in md
    assert vu.SENTINEL_END in md


def test_render_block_escapes_pipes() -> None:
    md = vu.render_block([
        {
            "video_id": "abc",
            "published_at": "2026-05-14",
            "title": "Title|with|pipes",
            "rel_path": "Videos/x.md",
            "summary": "BTC|ETH",
        },
    ])
    assert "Title\\|with\\|pipes" in md
    assert "BTC\\|ETH" in md


# ---------------------------------------------------------------------------
# Upsert — preserves operator content, idempotent, FIFO at cap
# ---------------------------------------------------------------------------


def test_upsert_creates_file_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "_index.md"
    ok = vu.upsert(path, new_entry={
        "video_id": "v1",
        "published_at": "2026-05-14",
        "title": "First Video",
        "rel_path": "Videos/test/v1.md",
        "summary": "BTC (4h)",
    }, rollup_cap=10)
    assert ok is True
    content = path.read_text()
    assert vu.SENTINEL_START in content
    assert "First Video" in content


def test_upsert_preserves_operator_content_above_and_below(tmp_path: Path) -> None:
    path = tmp_path / "_index.md"
    path.write_text(
        "# Operator-authored heading\n\n"
        "Some manual notes here.\n\n"
        f"{vu.SENTINEL_START}\nold inner\n{vu.SENTINEL_END}\n\n"
        "More operator notes below.\n"
    )
    ok = vu.upsert(path, new_entry={
        "video_id": "v1",
        "published_at": "2026-05-14",
        "title": "Test",
        "rel_path": "Videos/test/v1.md",
        "summary": "ETH (1d)",
    }, rollup_cap=10)
    assert ok is True
    content = path.read_text()
    # Above + below preserved.
    assert "# Operator-authored heading" in content
    assert "Some manual notes here." in content
    assert "More operator notes below." in content
    # Block replaced with fresh entry.
    assert "old inner" not in content
    assert "Test" in content


def test_upsert_is_idempotent(tmp_path: Path) -> None:
    """Same video_id twice → only one row."""
    path = tmp_path / "_index.md"
    entry = {
        "video_id": "v1",
        "published_at": "2026-05-14",
        "title": "Test",
        "rel_path": "Videos/test/v1.md",
        "summary": "BTC (4h)",
    }
    vu.upsert(path, new_entry=entry, rollup_cap=10)
    vu.upsert(path, new_entry=entry, rollup_cap=10)
    content = path.read_text()
    # The title appears in the table exactly once.
    assert content.count("BTC (4h)") == 1


def test_upsert_fifo_eviction_at_cap(tmp_path: Path) -> None:
    """rollup_cap=2 → oldest gets evicted."""
    path = tmp_path / "_index.md"
    entries = [
        {"video_id": "v1", "published_at": "2026-05-10", "title": "Oldest", "rel_path": "x", "summary": "AAA"},
        {"video_id": "v2", "published_at": "2026-05-12", "title": "Middle", "rel_path": "y", "summary": "BBB"},
        {"video_id": "v3", "published_at": "2026-05-14", "title": "Newest", "rel_path": "z", "summary": "CCC"},
    ]
    for e in entries:
        vu.upsert(path, new_entry=e, rollup_cap=2)
    content = path.read_text()
    # Oldest evicted.
    assert "AAA" not in content
    assert "BBB" in content
    assert "CCC" in content


def test_upsert_dedupes_by_video_id_on_resubmit(tmp_path: Path) -> None:
    """Resubmit same video_id with different summary → row UPDATED in place."""
    path = tmp_path / "_index.md"
    vu.upsert(path, new_entry={
        "video_id": "v1", "published_at": "2026-05-14",
        "title": "Test", "rel_path": "x", "summary": "first-summary",
    }, rollup_cap=10)
    vu.upsert(path, new_entry={
        "video_id": "v1", "published_at": "2026-05-14",
        "title": "Test", "rel_path": "x", "summary": "updated-summary",
    }, rollup_cap=10)
    content = path.read_text()
    assert "first-summary" not in content
    assert "updated-summary" in content


def test_upsert_orders_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "_index.md"
    older = {"video_id": "v1", "published_at": "2026-05-10", "title": "Older", "rel_path": "x", "summary": "AAA"}
    newer = {"video_id": "v2", "published_at": "2026-05-14", "title": "Newer", "rel_path": "y", "summary": "BBB"}
    # Insert older first; then newer. Output should show newer above older.
    vu.upsert(path, new_entry=older, rollup_cap=10)
    vu.upsert(path, new_entry=newer, rollup_cap=10)
    content = path.read_text()
    assert content.index("Newer") < content.index("Older")


def test_channel_index_path_for() -> None:
    vault = Path("/vault")
    p = vu.channel_index_path_for(vault, "Videos/click-capital")
    assert p == Path("/vault/Videos/click-capital/_index.md")
