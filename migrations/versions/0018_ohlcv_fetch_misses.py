"""ohlcv_fetch_misses — track give-up after N for missing actuals

The accuracy evaluator hourly tick refreshes OHLCV when a pending
prediction's actual bar is absent. A bar that yfinance never publishes
(delisted ticker, holiday, exchange downtime) would otherwise be retried
hourly forever. This table caps attempts per (ticker, interval, target_ts)
so we stop hammering the upstream provider after a defined number of
attempts.

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ohlcv_fetch_misses",
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("target_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "ticker", "interval", "target_ts", name="pk_ohlcv_fetch_misses"
        ),
    )


def downgrade() -> None:
    op.drop_table("ohlcv_fetch_misses")
