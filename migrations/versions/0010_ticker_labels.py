"""ticker_labels EAV metadata table

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticker_labels",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["symbol"], ["tickers.symbol"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("symbol", "key", name="uq_ticker_labels_symbol_key"),
    )
    op.create_index("ix_ticker_labels_key", "ticker_labels", ["key"])


def downgrade() -> None:
    op.drop_index("ix_ticker_labels_key", table_name="ticker_labels")
    op.drop_table("ticker_labels")
