"""opportunities table — Phase 3.1 actionability bridge

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),  # 'buy' | 'sell'
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("source_prediction_id", sa.String(length=36), nullable=False),
        sa.Column("source_model_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=32), nullable=False),
        sa.Column("rule_label", sa.String(length=128), nullable=False),
        sa.Column("predicted_move_pct", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_reason", sa.String(length=256), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_prediction_id"], ["prediction_points.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "source_prediction_id", "rule_id", name="uq_opp_prediction_rule"
        ),
    )
    op.create_index("ix_opp_status", "opportunities", ["status"])
    op.create_index(
        "ix_opp_ticker_status", "opportunities", ["ticker", "status"]
    )
    op.create_index("ix_opp_generated_at", "opportunities", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_opp_generated_at", table_name="opportunities")
    op.drop_index("ix_opp_ticker_status", table_name="opportunities")
    op.drop_index("ix_opp_status", table_name="opportunities")
    op.drop_table("opportunities")
