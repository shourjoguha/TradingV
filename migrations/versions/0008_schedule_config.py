"""schedule_config singleton table

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tz_name", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("run_at_local", sa.Time(), nullable=False),
        sa.Column("intervals", sa.JSON(), nullable=False),
        sa.Column("horizon_bars", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("model_ids", sa.JSON(), nullable=False),
        sa.Column("retry_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "collect_actuals", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "skip_weekends", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "pending_run", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.Column("last_run_error", sa.Text(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Insert the singleton row with locked defaults.
    import json

    op.execute(
        sa.text(
            "INSERT INTO schedule_config "
            "(id, enabled, tz_name, run_at_local, intervals, horizon_bars, "
            " model_ids, retry_minutes, collect_actuals, skip_weekends, pending_run) "
            "VALUES (1, FALSE, 'UTC', '23:30:00', :intervals, 5, :model_ids, 5, TRUE, TRUE, FALSE)"
        ).bindparams(intervals=json.dumps(["1d"]), model_ids=json.dumps(["kronos_base"]))
    )


def downgrade() -> None:
    op.drop_table("schedule_config")
