"""tickers registry + backfill from alerts

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tickers" not in inspector.get_table_names():
        op.create_table(
            "tickers",
            sa.Column("symbol", sa.String(length=50), primary_key=True),
            sa.Column("asset_class", sa.String(length=16), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column(
                "first_seen",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "last_seen",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
        )

    # Backfill distinct tickers from alerts (asset_class defaulted to 'stock';
    # user can refine via PATCH. Safe, idempotent — INSERT OR IGNORE / ON CONFLICT.)
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            INSERT INTO tickers (symbol, asset_class, source)
            SELECT DISTINCT UPPER(TRIM(ticker)), 'stock', 'alert'
            FROM alerts
            WHERE ticker IS NOT NULL AND TRIM(ticker) <> ''
            ON CONFLICT (symbol) DO NOTHING
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            INSERT OR IGNORE INTO tickers (symbol, asset_class, source)
            SELECT DISTINCT UPPER(TRIM(ticker)), 'stock', 'alert'
            FROM alerts
            WHERE ticker IS NOT NULL AND TRIM(ticker) <> ''
            """
        )


def downgrade() -> None:
    op.drop_table("tickers")
