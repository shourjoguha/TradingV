"""Seed a per-ticker IR YouTube channel folder.

Reuses the existing channel-poller pattern (``youtube_channel.py``).
Resolves the handle to a channel ID (same trick we used for Click Capital
+ fx-evolution-daily), then writes ``<vault>/Videos/earnings-<ticker>/_channel.yaml``
with sensible defaults for earnings ingest:

  • weekly cadence (earnings only happen quarterly; daily wastes polls)
  • horizon_months: 3 (transcripts stale fast)
  • tags: [earnings, <TICKER>]
  • auto_promote: true (same as fx-evolution-daily)

Usage::

    python -m tools.vault_indexer.ingest.seed_ir_channel \\
        --ticker META --handle @meta

    # Multiple at once:
    python -m tools.vault_indexer.ingest.seed_ir_channel \\
        --ticker AAPL --handle @apple
    python -m tools.vault_indexer.ingest.seed_ir_channel \\
        --ticker NVDA --handle @nvidia

The script ONLY creates the folder + YAML. It does NOT trigger a poll.
The next lifespan-loop tick (or a manual ``youtube_channel`` run) will
discover the new folder and ingest available transcripts.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import yaml

from ..config import CONFIG

logger = logging.getLogger(__name__)


_CHANNEL_ID_PATTERNS = [
    re.compile(r'"externalId":"(UC[A-Za-z0-9_-]{20,})"'),
    re.compile(r'"channelId":"(UC[A-Za-z0-9_-]{20,})"'),
    re.compile(r'"browseId":"(UC[A-Za-z0-9_-]{20,})"'),
]


def resolve_channel_id_from_handle(handle: str) -> Optional[str]:
    """Resolve a YouTube ``@handle`` (or full URL) to a UC… channel ID by
    fetching the page and grepping the embedded JSON metadata.

    Same approach used to seed Click Capital. Doesn't require the API.
    """
    if handle.startswith("http"):
        url = handle
    else:
        bare = handle.lstrip("@")
        url = f"https://www.youtube.com/@{bare}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Safari/605.1.15"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:                                 # noqa: BLE001
        logger.warning("handle resolve failed for %s: %s", handle, e)
        return None

    for pattern in _CHANNEL_ID_PATTERNS:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def seed_folder(
    *,
    ticker: str,
    handle: str,
    vault_root: Optional[Path] = None,
    cadence: str = "weekly",
    horizon_months: int = 3,
    extra_tags: Optional[list[str]] = None,
) -> Path:
    """Create the channel folder + ``_channel.yaml``. Returns the YAML path.

    Idempotent: if the folder already exists with a different channel_id,
    the script raises (operator presumably wanted a different ticker
    folder). If the YAML matches, it's a no-op.
    """
    root = vault_root or CONFIG.vault_path
    ticker_u = ticker.upper().strip()
    handle_clean = handle.strip()
    if not handle_clean:
        raise ValueError("handle required")

    channel_id = resolve_channel_id_from_handle(handle_clean)
    if not channel_id:
        raise RuntimeError(
            f"could not resolve channel ID for handle {handle_clean!r}. "
            "Check the handle, or pass the full channel URL "
            "(https://www.youtube.com/channel/UC...)."
        )

    if handle_clean.startswith("http"):
        channel_url = handle_clean
    else:
        bare = handle_clean.lstrip("@")
        channel_url = f"https://www.youtube.com/@{bare}"

    folder_name = f"earnings-{ticker_u.lower()}"
    folder = root / "Videos" / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    yaml_path = folder / "_channel.yaml"
    cfg = {
        "channel_id": channel_id,
        "channel_url": channel_url,
        "author": f"{ticker_u} Investor Relations",
        "default_kind": "video",
        "default_horizon_months": horizon_months,
        "default_tags": ["earnings", ticker_u] + (extra_tags or []),
        "ingest": {
            "enabled": True,
            "cadence": cadence,
            "auto_promote": True,
            # IR channels post raw multi-hour calls; auto-captions on long-form
            # earnings calls are flaky. Default to manual_only so Whisper handles
            # them. Operator can flip to True per-channel for talkier IR teams.
            "prefer_captions": "manual_only",
            "seen_video_ids": [],
        },
        # Earnings trigger gate (Phase 2). Channel only polls during the
        # window around the ticker's earnings release. Multi-ticker channels
        # (e.g. Alphabet IR for GOOGL + GOOG) can extend the tickers list.
        "earnings_trigger": {
            "tickers": [ticker_u],
            "days_before": 0,
            "days_after": 3,
        },
    }

    if yaml_path.exists():
        existing = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        if existing.get("channel_id") == channel_id:
            logger.info(
                "%s already seeded with channel_id %s — leaving as-is",
                folder_name, channel_id,
            )
            return yaml_path
        raise RuntimeError(
            f"{yaml_path} already exists with a different channel_id "
            f"({existing.get('channel_id')!r}). Manually resolve before re-running."
        )

    yaml_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    logger.info("seeded %s → channel_id %s", yaml_path, channel_id)
    return yaml_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="seed_ir_channel")
    ap.add_argument("--ticker", required=True, help="Ticker symbol, e.g. META")
    ap.add_argument(
        "--handle",
        required=True,
        help="YouTube handle (e.g. @meta) or full channel URL.",
    )
    ap.add_argument(
        "--cadence",
        default="weekly",
        choices=["daily", "weekly", "biweekly"],
        help="Poll cadence (default: weekly — earnings are quarterly so daily wastes polls).",
    )
    ap.add_argument(
        "--horizon-months",
        type=int,
        default=3,
        help="Decay horizon for the channel's chunks (default: 3 months).",
    )
    ap.add_argument(
        "--tag",
        action="append",
        dest="extra_tags",
        default=None,
        help="Add extra tags (repeatable). Default tags are 'earnings' + the ticker.",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        path = seed_folder(
            ticker=args.ticker,
            handle=args.handle,
            cadence=args.cadence,
            horizon_months=args.horizon_months,
            extra_tags=args.extra_tags,
        )
        print(f"✓ {path}")
        return 0
    except Exception as e:                                 # noqa: BLE001
        print(f"✗ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
