"""recommendations.attention_score + attention_breakdown (rx v1.x.1-e).

Phase 2 of `tv-context-decision-engine-enrichment` plan: rx-finance recs
get a visible "operator attention" axis derived from TV-context inputs
(notes / ideas / screenshots / events) in the trailing 14d. Surfaces in
the rec detail UI as a badge: "👁️ Operator attention: N screenshots +
M notes in last 14d".

Two columns, both nullable + additive:
  - attention_score FLOAT — weighted-sum across kinds w/ exp(-age/halflife)
  - attention_breakdown JSON — `{ticker: {kind: count, score: float}}` per
    matched ticker. Plural because a rec may mention 2+ tickers; we store
    the full breakdown so the UI can render "NVDA: 3 screenshots; META:
    1 note" rather than a single opaque number.

Picks design B from the plan (explicit attention axis on the rec) over
A (composite-score modulation) because decision-engine changes that
aren't visible are anti-product. The badge teaches the operator why a
rec ranked here.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(
            sa.Column("attention_score", sa.Float(), nullable=True)
        )
        batch.add_column(
            sa.Column("attention_breakdown", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_column("attention_breakdown")
        batch.drop_column("attention_score")
