"""prediction_accuracy table — Phase 1.1 trust through feedback

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_accuracy",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("prediction_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("horizon_offset", sa.SmallInteger(), nullable=False),
        sa.Column("made_on", sa.Date(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("predicted_close", sa.Float(), nullable=False),
        sa.Column("actual_close", sa.Float(), nullable=False),
        sa.Column("baseline_close", sa.Float(), nullable=True),
        sa.Column("error_pct", sa.Float(), nullable=False),
        sa.Column("abs_error_pct", sa.Float(), nullable=False),
        sa.Column("squared_error", sa.Float(), nullable=False),
        sa.Column("direction_correct", sa.Boolean(), nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["prediction_id"], ["prediction_points.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_pa_ticker_horizon", "prediction_accuracy", ["ticker", "horizon_offset"]
    )
    op.create_index(
        "ix_pa_evaluated_at", "prediction_accuracy", [sa.text("evaluated_at DESC")]
    )
    op.create_index(
        "ix_pa_ticker_evaluated",
        "prediction_accuracy",
        ["ticker", sa.text("evaluated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_pa_ticker_evaluated", table_name="prediction_accuracy")
    op.drop_index("ix_pa_evaluated_at", table_name="prediction_accuracy")
    op.drop_index("ix_pa_ticker_horizon", table_name="prediction_accuracy")
    op.drop_table("prediction_accuracy")
