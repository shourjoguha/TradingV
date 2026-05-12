"""Vault retention sweep for SEC EDGAR filings.

Policy:
  - 10-Q / 10-K: keep forever (low volume; permanent reference value)
  - 8-K: drop when older than 18 months (high volume, fades fast)
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Optional

import frontmatter

from .config import CONFIG


logger = logging.getLogger(__name__)


EIGHT_K_TTL_DAYS = 18 * 30  # ≈ 18 months


def cleanup_old_8k(
    vault_root: Optional[Path] = None,
    *,
    ttl_days: int = EIGHT_K_TTL_DAYS,
) -> int:
    """Walk Filings/<TICKER>/ and delete 8-K markdown files older than TTL.

    Returns the count of files deleted. Idempotent.
    """
    root = vault_root or CONFIG.vault_path
    folder = root / "Filings"
    if not folder.exists():
        return 0
    cutoff = datetime.date.today() - datetime.timedelta(days=ttl_days)
    deleted = 0
    for path in folder.rglob("*.md"):
        try:
            post = frontmatter.load(str(path))
        except Exception:  # noqa: BLE001
            continue
        form_type = (post.get("form_type") or post.get("form") or "").upper()
        if "8-K" not in form_type and "8K" not in form_type:
            continue
        filed_at = post.get("filed_at") or post.get("date")
        if not filed_at:
            continue
        try:
            d = datetime.date.fromisoformat(str(filed_at)[:10])
        except (TypeError, ValueError):
            continue
        if d < cutoff:
            try:
                path.unlink()
                deleted += 1
            except OSError as e:
                logger.warning("could not delete %s: %s", path, e)
    return deleted
