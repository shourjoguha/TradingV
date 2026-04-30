"""boards + board_tickers tables; lightweight quote columns on ticker_market_data

Phase MW-2 of the multi-watchlist work. Adds casual lists ("boards" in
schema, "Watchlists" in UI) + a single-quote-per-ticker shape on the
existing ticker_market_data table so casual lists, Dashboard tiles, and
the sector drill-in all read from one source of truth.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "boards",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
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
        sa.UniqueConstraint("name", name="uq_boards_name"),
    )

    op.create_table(
        "board_tickers",
        sa.Column(
            "board_id",
            sa.String(length=36),
            sa.ForeignKey("boards.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "ticker",
            sa.String(length=50),
            sa.ForeignKey("tickers.symbol", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_board_tickers_ticker",
        "board_tickers",
        ["ticker"],
    )

    # Lightweight quote columns on ticker_market_data. NULL-safe — existing
    # rows just have None until the next refresh tick fills them.
    op.add_column(
        "ticker_market_data",
        sa.Column("last_close", sa.Numeric(20, 6), nullable=True),
    )
    op.add_column(
        "ticker_market_data",
        sa.Column("last_close_at", sa.Date(), nullable=True),
    )
    op.add_column(
        "ticker_market_data",
        sa.Column("pct_1w", sa.Numeric(10, 4), nullable=True),
    )
    op.add_column(
        "ticker_market_data",
        sa.Column(
            "quote_fetched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("ticker_market_data", "quote_fetched_at")
    op.drop_column("ticker_market_data", "pct_1w")
    op.drop_column("ticker_market_data", "last_close_at")
    op.drop_column("ticker_market_data", "last_close")
    op.drop_index("ix_board_tickers_ticker", table_name="board_tickers")
    op.drop_table("board_tickers")
    op.drop_table("boards")
