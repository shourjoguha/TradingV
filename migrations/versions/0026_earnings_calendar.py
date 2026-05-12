"""earnings_calendar — Phase 2 of the cost-aware iteration.

Stores expected (and confirmed-via-EDGAR) earnings dates for the union of
roster ∪ Street Tier 1+2 last 4 snapshots, capped at 150 tickers, with a
90-day TTL after a ticker last appears in the universe.

The IR YouTube channel poller reads this table to decide whether today is
within the trigger window for a given channel — saving Whisper CPU on
non-earnings days.

Replicates to the Railway peer via the sync outbox so the Today panel
works on either side.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "earnings_calendar",
        sa.Column("ticker", sa.String(length=50), primary_key=True),
        sa.Column("expected_at", sa.Date(), nullable=True),
        sa.Column("confirmed_at", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_universe_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_earnings_calendar_expected_at",
        "earnings_calendar",
        ["expected_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_earnings_calendar_expected_at", table_name="earnings_calendar")
    op.drop_table("earnings_calendar")
