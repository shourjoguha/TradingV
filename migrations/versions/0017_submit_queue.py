"""submit_queue table — Tier 1 job submission queue

Replaces the inline-with-429 pattern. POST /v1/analysis/run inserts a
queue row + returns 202; a single worker drains FIFO. Schedule runner
enqueues like any other caller.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "submit_queue",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("inputs_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"], ["analysis_jobs.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_queue_pending", "submit_queue", ["status", "enqueued_at"]
    )
    op.create_index(
        "ix_queue_recent", "submit_queue", ["enqueued_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_queue_recent", table_name="submit_queue")
    op.drop_index("ix_queue_pending", table_name="submit_queue")
    op.drop_table("submit_queue")
