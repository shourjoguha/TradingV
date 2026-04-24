"""analysis_jobs + analysis_tasks

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "analysis_jobs" not in existing:
        op.create_table(
            "analysis_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("inputs_json", sa.JSON(), nullable=False),
            sa.Column("task_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "submitted_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "analysis_tasks" not in existing:
        op.create_table(
            "analysis_tasks",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "job_id",
                sa.String(length=36),
                sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("ticker", sa.String(length=50), nullable=False),
            sa.Column("interval", sa.String(length=8), nullable=False),
            sa.Column("model_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("ineligible_reason", sa.String(length=32), nullable=True),
            sa.Column("ineligible_message", sa.String(length=500), nullable=True),
            sa.Column("error", sa.String(length=500), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_analysis_tasks_job_id", "analysis_tasks", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_tasks_job_id", table_name="analysis_tasks")
    op.drop_table("analysis_tasks")
    op.drop_table("analysis_jobs")
