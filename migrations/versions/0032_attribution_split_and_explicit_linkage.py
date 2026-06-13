"""Attribution split + explicit hypothesis linkage (retrieval-depth Phase 4).

Two additive columns that de-bias the feedback loop:

  1. ``trades.rec_influence_kind`` — distinguishes a trade the rec PREDICTED
     (operator decided independently) from one the rec CAUSED. Excluding the
     ``influenced`` trades from predictive-lift breaks limitation B4: the
     self-influence flywheel where a rec gets P&L credit for a move it caused
     the operator to make, which then reads as "the model is learning".
     Values: 'preceded_independent' | 'influenced' | NULL (unclassified/legacy).

  2. ``recommendations.linked_hypothesis_ids`` — explicit JSON list of the
     hypothesis ids a rec acts on, populated at compose time. Replaces the
     false-positive-prone substring match (D2) as the PRIMARY linkage; the
     substring heuristic stays only as a fallback suggestion. Nullable +
     additive so legacy rows keep working.

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trades") as batch:
        batch.add_column(
            sa.Column("rec_influence_kind", sa.String(24), nullable=True)
        )
        batch.create_check_constraint(
            "ck_trades_rec_influence_kind",
            "rec_influence_kind IS NULL OR "
            "rec_influence_kind IN ('preceded_independent','influenced')",
        )
    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(
            sa.Column("linked_hypothesis_ids", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_column("linked_hypothesis_ids")
    with op.batch_alter_table("trades") as batch:
        batch.drop_constraint("ck_trades_rec_influence_kind", type_="check")
        batch.drop_column("rec_influence_kind")
