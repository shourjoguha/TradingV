"""Earnings-trigger gate inside the YouTube channel poller."""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import yaml

from tools.vault_indexer.ingest import youtube_channel as _yt


def _write_channel(tmp_path: Path, *, earnings_trigger=None, last_polled_at=None) -> Path:
    folder = tmp_path / "Videos" / "earnings-meta"
    folder.mkdir(parents=True, exist_ok=True)
    cfg = {
        "channel_id": "UCfake",
        "channel_url": "https://youtube.com/@meta",
        "author": "META Investor Relations",
        "default_kind": "video",
        "default_tags": ["earnings", "META"],
        "ingest": {
            "enabled": True,
            "cadence": "daily",
            "auto_promote": True,
            "prefer_captions": "manual_only",
            "seen_video_ids": [],
        },
    }
    if earnings_trigger is not None:
        cfg["earnings_trigger"] = earnings_trigger
    if last_polled_at:
        cfg["ingest"]["last_polled_at"] = last_polled_at
    (folder / "_channel.yaml").write_text(yaml.safe_dump(cfg))
    return folder


def test_no_trigger_block_polls_normally(tmp_path, monkeypatch):
    folder = _write_channel(tmp_path)
    # is_due() will be True because no last_polled_at. fetch_feed mocked.
    fetched = []

    def _stub_fetch(channel_id):
        fetched.append(channel_id)
        return []

    monkeypatch.setattr(_yt, "fetch_feed", _stub_fetch)
    result = _yt.ingest_one(
        channel_dir=folder,
        vault_root=tmp_path,
        max_videos_per_run=0,
    )
    assert result.get("reason") != "earnings_trigger_gate_closed"


def test_trigger_block_skips_when_outside_window(tmp_path, monkeypatch):
    far_past = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    folder = _write_channel(
        tmp_path,
        earnings_trigger={
            "tickers": ["META"],
            "days_before": 0,
            "days_after": 3,
        },
    )

    fetched: list[str] = []

    def _stub_fetch(channel_id):
        fetched.append(channel_id)
        return []

    monkeypatch.setattr(_yt, "fetch_feed", _stub_fetch)
    # earnings_dates indicates META released earnings 60 days ago — out of window.
    result = _yt.ingest_one(
        channel_dir=folder,
        vault_root=tmp_path,
        max_videos_per_run=0,
        earnings_dates={"META": datetime.date.fromisoformat(far_past)},
    )
    assert result["reason"] == "earnings_trigger_gate_closed"
    assert result["drafts_written"] == 0
    assert fetched == []  # Never even hit the feed.


def test_trigger_block_polls_when_inside_window(tmp_path, monkeypatch):
    today = datetime.date.today()
    folder = _write_channel(
        tmp_path,
        earnings_trigger={
            "tickers": ["META"],
            "days_before": 0,
            "days_after": 3,
        },
    )
    fetched: list[str] = []

    def _stub_fetch(channel_id):
        fetched.append(channel_id)
        return []

    monkeypatch.setattr(_yt, "fetch_feed", _stub_fetch)
    result = _yt.ingest_one(
        channel_dir=folder,
        vault_root=tmp_path,
        max_videos_per_run=0,
        earnings_dates={"META": today},
    )
    assert result.get("reason") != "earnings_trigger_gate_closed"
    assert fetched == ["UCfake"]


def test_trigger_block_no_dates_skips(tmp_path, monkeypatch):
    folder = _write_channel(
        tmp_path,
        earnings_trigger={"tickers": ["META"], "days_before": 0, "days_after": 3},
    )
    monkeypatch.setattr(_yt, "fetch_feed", lambda _: [])
    result = _yt.ingest_one(
        channel_dir=folder,
        vault_root=tmp_path,
        max_videos_per_run=0,
        earnings_dates={},
    )
    assert result["reason"] == "earnings_trigger_gate_closed"
