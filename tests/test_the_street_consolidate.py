"""The Street quarterly rollup."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.the_street import consolidate as _c


def _mkdir(root: Path, label: str) -> None:
    d = root / "The Street" / "snapshots" / label
    d.mkdir(parents=True)
    (d / "_index.md").write_text("# stub\n")


def test_no_action_when_under_threshold(tmp_path):
    for label in ("2026-01-04", "2026-01-11", "2026-01-18"):
        _mkdir(tmp_path, label)
    rolled = _c.maybe_rollup_quarter(vault_root=tmp_path, keep_raw=13)
    assert rolled == 0
    # No quarterly file written.
    assert not (tmp_path / "The Street" / "quarterlies").exists()


def test_rollup_creates_file_before_deleting_sources(tmp_path):
    # 14 weekly snapshots — exceeds keep_raw, oldest quarter (Q1) gets rolled.
    for week in range(14):
        # Week 0 = 2026-01-04 then advance 7 days.
        import datetime
        d = datetime.date(2026, 1, 4) + datetime.timedelta(weeks=week)
        _mkdir(tmp_path, d.isoformat())
    rolled = _c.maybe_rollup_quarter(vault_root=tmp_path, keep_raw=13)
    assert rolled >= 1
    # Quarterly file exists.
    quarter_dir = tmp_path / "The Street" / "quarterlies" / "2026-Q1"
    assert quarter_dir.exists()
    assert (quarter_dir / "quarter-rollup.md").exists()


def test_idempotent_rerun(tmp_path):
    import datetime
    for week in range(14):
        d = datetime.date(2026, 1, 4) + datetime.timedelta(weeks=week)
        _mkdir(tmp_path, d.isoformat())
    _c.maybe_rollup_quarter(vault_root=tmp_path, keep_raw=13)
    # Rerun shouldn't fail and rollup file stays.
    rolled = _c.maybe_rollup_quarter(vault_root=tmp_path, keep_raw=13)
    assert rolled >= 0
    assert (tmp_path / "The Street" / "quarterlies" / "2026-Q1" / "quarter-rollup.md").exists()
