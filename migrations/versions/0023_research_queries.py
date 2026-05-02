"""research_queries — Phase 3 stress-test audit log.

Each call to POST /v1/research/ask persists a row: query, bundle hash,
Claude response, proposed action (if any), token cost, and approval
status. Backs the GET /v1/research/queries history surface and lets the
indexer's research-tick hook map a markdown answer file back to the
server-side row by uuid.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_queries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("query", sa.Text(), nullable=False),
        # JSON not JSONB: SQLite test parity. List of slugs OR row ids.
        sa.Column("hypothesis_ids", sa.JSON(), nullable=False),
        sa.Column("answer_path", sa.String(length=500), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("est_cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("bundle", sa.JSON(), nullable=True),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_action", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'dismissed', 'error')",
            name="ck_research_queries_status",
        ),
    )
    op.create_index(
        "ix_research_queries_asked_at",
        "research_queries",
        ["asked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_queries_asked_at", table_name="research_queries")
    op.drop_table("research_queries")
