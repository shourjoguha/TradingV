"""research_queries scoring + auto-defer + auto-age columns.

Supports the Today landing redesign — top-5 visible by composite score
(not chronology), with deferred queries staying pending in the backlog
but out of the landing view. Idle pending queries auto-dismiss after
30 days via the retention loop.

Adds three columns:
  - score FLOAT NULL — composite priority score, NULL = not yet computed
  - is_deferred BOOLEAN NOT NULL DEFAULT FALSE — true when query is in
    the backlog (outside current top-5)
  - auto_aged_at TIMESTAMPTZ NULL — set when retention sweep auto-aged
    a pending query into dismissed; null otherwise

Plus a composite index on (status, is_deferred, score DESC) for the
top-5 query path.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("research_queries") as batch:
        batch.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column(
                "is_deferred",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column("auto_aged_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_index(
        "ix_research_queries_status_deferred_score",
        "research_queries",
        ["status", "is_deferred", sa.text("score DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_queries_status_deferred_score",
        table_name="research_queries",
    )
    with op.batch_alter_table("research_queries") as batch:
        batch.drop_column("auto_aged_at")
        batch.drop_column("is_deferred")
        batch.drop_column("score")
