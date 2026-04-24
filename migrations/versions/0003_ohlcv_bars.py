"""ohlcv_bars cache table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "ohlcv_bars" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "ohlcv_bars",
        sa.Column("symbol", sa.String(length=50), primary_key=True),
        sa.Column("interval", sa.String(length=8), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Helpful composite index for "latest N bars" queries.
    op.create_index(
        "ix_ohlcv_symbol_interval_ts_desc",
        "ohlcv_bars",
        ["symbol", "interval", sa.text("ts DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_ohlcv_symbol_interval_ts_desc", table_name="ohlcv_bars")
    op.drop_table("ohlcv_bars")
