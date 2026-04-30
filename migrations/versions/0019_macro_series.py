"""macro_series — daily macro time-series cache (yfinance + FRED)

Foundation for the Macro Workbench (Phase M-1). Stores one row per
``(symbol, ts)`` so ratios + slow regime indicators can be queried without
hitting upstream every time. Ratios are computed at query time, not
materialised, so this table is the only schema needed for M-1.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "macro_series",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("ts", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("symbol", "ts", name="uq_macro_series_symbol_ts"),
        sa.CheckConstraint(
            "source IN ('yfinance', 'fred', 'manual')",
            name="ck_macro_series_source",
        ),
    )
    op.create_index(
        "ix_macro_series_symbol_ts",
        "macro_series",
        ["symbol", sa.text("ts DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_macro_series_symbol_ts", table_name="macro_series")
    op.drop_table("macro_series")
