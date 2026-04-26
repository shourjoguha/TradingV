"""prediction_points flat forecast table

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_points",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("made_on", sa.Date(), nullable=False),
        sa.Column("made_on_dow", sa.SmallInteger(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("target_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_offset", sa.SmallInteger(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_pp_target_ticker", "prediction_points", ["target_date", "ticker"]
    )
    op.create_index(
        "ix_pp_made_on_ticker", "prediction_points", ["made_on", "ticker"]
    )
    op.create_index(
        "ix_pp_ticker_target_made",
        "prediction_points",
        ["ticker", "target_date", "made_on"],
    )
    op.create_index("ix_pp_made_on_dow", "prediction_points", ["made_on_dow"])


def downgrade() -> None:
    op.drop_index("ix_pp_made_on_dow", table_name="prediction_points")
    op.drop_index("ix_pp_ticker_target_made", table_name="prediction_points")
    op.drop_index("ix_pp_made_on_ticker", table_name="prediction_points")
    op.drop_index("ix_pp_target_ticker", table_name="prediction_points")
    op.drop_table("prediction_points")
