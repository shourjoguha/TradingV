"""Shared helpers: slug, frontmatter writer, vault path resolution."""
from __future__ import annotations

import datetime
import re
from pathlib import Path

import frontmatter


def slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "untitled"


def write_note(
    *,
    vault_root: Path,
    rel_dir: str,                   # e.g. "Newsletters/lyn-alden"
    filename: str,                  # e.g. "2026-w19.md"
    body: str,
    metadata: dict,
) -> Path:
    target_dir = vault_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    metadata = {**metadata, "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    post = frontmatter.Post(content=body, **metadata)
    target.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return target


def iso_week(d: datetime.date | None = None) -> str:
    d = d or datetime.date.today()
    iso = d.isocalendar()
    return f"{iso.year}-w{iso.week:02d}"
