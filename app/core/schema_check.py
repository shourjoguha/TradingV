"""Boot-time schema-version check.

Reads ``alembic_version.version_num`` from the connected DB and compares
against the highest-numbered file under ``migrations/versions/``. Logs a
loud ``WARN`` if they differ. Doesn't mutate, doesn't raise — the boot
still proceeds. Operator decides whether to run ``alembic upgrade head``.

This replaces the old ``Base.metadata.create_all`` parity-net in lifespan,
which silently auto-created tables and masked schema drift. See ADR-013
operator decision and ADR-014 second-occurrence note; backlog entry
"Move ``Base.metadata.create_all`` out of lifespan; add boot-time
alembic-version warning" — this module is the second half of that.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_MIGRATION_PREFIX = re.compile(r"^(\d{4})_")


def latest_revision_on_disk(migrations_dir: Optional[Path] = None) -> Optional[str]:
    """Return the highest 4-digit revision id under ``migrations/versions/``.

    None if the directory doesn't exist or contains no matching files.
    """
    base = migrations_dir or (
        Path(__file__).resolve().parent.parent.parent / "migrations" / "versions"
    )
    if not base.is_dir():
        return None
    ids: list[str] = []
    for p in base.iterdir():
        if p.suffix != ".py":
            continue
        m = _MIGRATION_PREFIX.match(p.stem)
        if m:
            ids.append(m.group(1))
    return max(ids) if ids else None


async def current_db_revision(engine: AsyncEngine) -> Optional[str]:
    """Return the ``alembic_version.version_num`` from the live DB.

    None when the table doesn't exist (fresh DB) or any DB error fires —
    we never want this check to raise.
    """
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            ).first()
            return row[0] if row else None
    except Exception:                                  # noqa: BLE001
        return None


async def warn_if_drift(engine: AsyncEngine) -> None:
    """Log a WARN when on-disk revision ≠ DB revision. Never raises.

    Three states worth distinguishing:
      - DB has no alembic_version row → "fresh DB; run alembic upgrade head"
      - DB version != latest on disk → "schema drift; run alembic upgrade head"
      - Match → no log
    """
    on_disk = latest_revision_on_disk()
    in_db = await current_db_revision(engine)
    if on_disk is None:
        # No migrations directory found — we're probably running outside
        # the repo (tests, packaged artifact, etc.). Don't warn.
        return
    if in_db is None:
        logger.warning(
            "[schema] alembic_version table missing or empty. Latest "
            "revision on disk is %s. Run `alembic upgrade head` before "
            "boot — `Base.metadata.create_all` is no longer applied at "
            "lifespan to surface this kind of drift.",
            on_disk,
        )
        return
    if in_db != on_disk:
        logger.warning(
            "[schema] DB at revision %s; latest on disk is %s. Run "
            "`alembic upgrade head` to apply pending migrations.",
            in_db, on_disk,
        )
