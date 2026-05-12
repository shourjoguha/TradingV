"""admin — app_settings + process_status.

Adds two tiny tables that back the cost-aware iteration's Admin shell:

- ``app_settings``: key/value JSONB store. Cascade order in service code is
  DB > env > hardcoded default. DB row wins; env-var seeds first boot.
- ``process_status``: one row per registered lifespan loop. Updated on every
  tick boundary via ``_record_tick``. Drives the Processes tab UI.

Both tables are per-instance state (laptop and Railway each have their own).
Neither replicates via the sync outbox.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "process_status",
        sa.Column("loop_id", sa.String(length=64), primary_key=True),
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tick_ok", sa.Boolean(), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("process_status")
    op.drop_table("app_settings")
