"""trades table — Phase 5 trade journal

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("opportunity_id", sa.String(length=36), nullable=True),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),  # 'buy' | 'sell'
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("fees", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes_md", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_trades_ticker", "trades", ["ticker"])
    op.create_index("ix_trades_entry_at", "trades", ["entry_at"])
    op.create_index("ix_trades_opportunity", "trades", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_trades_opportunity", table_name="trades")
    op.drop_index("ix_trades_entry_at", table_name="trades")
    op.drop_index("ix_trades_ticker", table_name="trades")
    op.drop_table("trades")
