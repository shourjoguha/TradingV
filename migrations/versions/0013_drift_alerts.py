"""drift_alerts table — Phase 1.3 trust-sprint drift detection

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drift_alerts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("horizon_offset", sa.SmallInteger(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("recent_mape", sa.Float(), nullable=False),
        sa.Column("all_time_mape", sa.Float(), nullable=False),
        sa.Column("ratio", sa.Float(), nullable=False),
        sa.Column("recent_sample_count", sa.Integer(), nullable=False),
        sa.Column("all_time_sample_count", sa.Integer(), nullable=False),
        sa.Column(
            "flagged_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_drift_open", "drift_alerts", ["acknowledged_at", "ticker"])
    op.create_index(
        "ix_drift_ticker_horizon", "drift_alerts", ["ticker", "horizon_offset"]
    )


def downgrade() -> None:
    op.drop_index("ix_drift_ticker_horizon", table_name="drift_alerts")
    op.drop_index("ix_drift_open", table_name="drift_alerts")
    op.drop_table("drift_alerts")
