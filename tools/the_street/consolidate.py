"""Quarterly rollup of The Street weekly snapshots.

Keeps the last 13 weekly snapshots in raw form; older quarters are
consolidated into a single ``<vault>/The Street/quarterlies/<YYYY-QN>/quarter-rollup.md``
file. Source weekly snapshots are deleted **only after** the rollup file
is successfully written.
"""
from __future__ import annotations

import datetime
import logging
import shutil
from pathlib import Path
from typing import Optional

from tools.vault_indexer.config import CONFIG


logger = logging.getLogger(__name__)


KEEP_RAW_SNAPSHOTS = 13


def _quarter_label(d: datetime.date) -> str:
    quarter = (d.month - 1) // 3 + 1
    return f"{d.year}-Q{quarter}"


def _quarter_bounds(year: int, quarter: int) -> tuple[datetime.date, datetime.date]:
    start_month = (quarter - 1) * 3 + 1
    start = datetime.date(year, start_month, 1)
    if quarter == 4:
        end = datetime.date(year + 1, 1, 1)
    else:
        end = datetime.date(year, start_month + 3, 1)
    return start, end


def list_snapshot_dirs(vault_root: Optional[Path] = None) -> list[Path]:
    root = (vault_root or CONFIG.vault_path) / "The Street" / "snapshots"
    if not root.exists():
        return []
    return sorted(
        [p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")]
    )


def maybe_rollup_quarter(
    vault_root: Optional[Path] = None,
    *,
    keep_raw: int = KEEP_RAW_SNAPSHOTS,
) -> int:
    """If we have more than ``keep_raw`` snapshots, roll up the oldest quarter
    into a markdown summary and delete the source dirs. Returns the count of
    snapshot dirs rolled up.

    Idempotent: if the quarterly rollup file already exists, just delete the
    sources and move on.
    """
    root = vault_root or CONFIG.vault_path
    dirs = list_snapshot_dirs(root)
    if len(dirs) <= keep_raw:
        return 0

    # Group by quarter, take the oldest fully-rollable quarter (oldest dir's quarter).
    try:
        oldest = datetime.date.fromisoformat(dirs[0].name)
    except ValueError:
        return 0
    label = _quarter_label(oldest)
    year, q = int(label.split("-")[0]), int(label[-1])
    qstart, qend = _quarter_bounds(year, q)

    in_quarter: list[Path] = []
    for d in dirs:
        try:
            day = datetime.date.fromisoformat(d.name)
        except ValueError:
            continue
        if qstart <= day < qend:
            in_quarter.append(d)
    if not in_quarter:
        return 0

    quarter_dir = root / "The Street" / "quarterlies" / label
    quarter_dir.mkdir(parents=True, exist_ok=True)
    rollup_path = quarter_dir / "quarter-rollup.md"

    if not rollup_path.exists():
        body = _render_rollup(label, in_quarter)
        rollup_path.write_text(body, encoding="utf-8")
        logger.info("wrote quarterly rollup: %s", rollup_path)

    # Delete source weekly dirs only after the rollup is on disk.
    deleted = 0
    for d in in_quarter:
        try:
            shutil.rmtree(d)
            deleted += 1
        except OSError as e:
            logger.warning("could not delete %s: %s", d, e)
    return deleted


def _render_rollup(label: str, dirs: list[Path]) -> str:
    """Cheap, deterministic rollup: list snapshot dates + their _index.md
    front-matter (if present). Operator can re-render later with richer
    diff-of-tier-1-rosters logic; this is the v1 baseline.
    """
    lines = [
        f"---",
        f"kind: quarter-rollup",
        f"quarter: {label}",
        f"snapshots: {len(dirs)}",
        f"first: {dirs[0].name}",
        f"last: {dirs[-1].name}",
        f"---",
        f"",
        f"# The Street — {label} rollup",
        f"",
        f"Aggregates {len(dirs)} weekly snapshots from "
        f"{dirs[0].name} → {dirs[-1].name}.",
        f"",
        f"## Snapshots included",
        f"",
    ]
    for d in dirs:
        lines.append(f"- {d.name}")
    lines.append("")
    return "\n".join(lines)
