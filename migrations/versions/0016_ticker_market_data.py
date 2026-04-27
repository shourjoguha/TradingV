"""ticker_market_data — Phase 6 options runway data layer

Stores per-ticker derived metrics (IV percentile, earnings dates, etc.).
Separate from `tickers` so the registry stays minimal and this can grow
independently as the options chapter expands.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticker_market_data",
        sa.Column("symbol", sa.String(length=50), primary_key=True),
        sa.Column("iv_30d", sa.Float(), nullable=True),
        sa.Column("iv_percentile_1y", sa.Float(), nullable=True),
        sa.Column("next_earnings_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String(length=256), nullable=True),
        sa.ForeignKeyConstraint(["symbol"], ["tickers.symbol"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_tmd_iv_percentile", "ticker_market_data", ["iv_percentile_1y"]
    )


def downgrade() -> None:
    op.drop_index("ix_tmd_iv_percentile", table_name="ticker_market_data")
    op.drop_table("ticker_market_data")
