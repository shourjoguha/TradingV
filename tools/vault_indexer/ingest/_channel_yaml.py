"""Load/save helpers for `_channel.yaml` — per-channel auto-ingest config.

The vault is canonical. Each channel folder under `Videos/<channel>/` may contain:
  _channel.yaml   ← machine-managed; operator edits cadence + auto_promote.

Schema (see `.claude/plans/video-channel-auto-ingest.md`):
  channel_id: UCxxxxx
  channel_url: https://youtube.com/...
  author: <name>
  default_kind: video
  default_horizon_months: 6
  default_tags: [macro, fx]
  ingest:
    enabled: true
    cadence: daily | weekly | manual
    auto_promote: false
    prefer_captions: true
    last_polled_at: <ISO>          # machine-managed
    last_video_id: <yt-id>          # machine-managed
    seen_video_ids: [<id1>, ...]    # rolling window, last 50
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Optional

import yaml


CHANNEL_FILE = "_channel.yaml"
SEEN_WINDOW = 50


def load(channel_dir: Path) -> Optional[dict[str, Any]]:
    """Read _channel.yaml. Returns None if absent."""
    target = channel_dir / CHANNEL_FILE
    if not target.exists():
        return None
    try:
        with target.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def save(channel_dir: Path, cfg: dict[str, Any]) -> None:
    """Write _channel.yaml with deterministic key order for clean git diffs."""
    target = channel_dir / CHANNEL_FILE
    with target.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


def is_due(cfg: dict[str, Any], *, now: Optional[datetime.datetime] = None) -> bool:
    """True if the channel is enabled, has a non-manual cadence, and the elapsed
    time since `last_polled_at` exceeds the cadence interval."""
    ingest = cfg.get("ingest") or {}
    if not ingest.get("enabled", False):
        return False
    cadence = (ingest.get("cadence") or "").lower()
    if cadence not in ("daily", "weekly"):
        return False
    last = ingest.get("last_polled_at")
    if not last:
        return True
    try:
        last_dt = datetime.datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    interval = datetime.timedelta(days=1 if cadence == "daily" else 7)
    return (now - last_dt) >= interval


def mark_polled(cfg: dict[str, Any], *, video_ids: list[str]) -> dict[str, Any]:
    """Record a successful poll. Stamps `last_polled_at`, prepends new
    video_ids into the rolling `seen_video_ids` window."""
    ingest = dict(cfg.get("ingest") or {})
    ingest["last_polled_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    seen = list(ingest.get("seen_video_ids") or [])
    if video_ids:
        ingest["last_video_id"] = video_ids[0]
        merged: list[str] = []
        for v in list(video_ids) + seen:
            if v not in merged:
                merged.append(v)
        ingest["seen_video_ids"] = merged[:SEEN_WINDOW]
    return {**cfg, "ingest": ingest}


def has_seen(cfg: dict[str, Any], video_id: str) -> bool:
    ingest = cfg.get("ingest") or {}
    return video_id in (ingest.get("seen_video_ids") or [])
