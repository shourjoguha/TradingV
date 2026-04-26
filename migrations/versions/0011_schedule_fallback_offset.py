"""schedule_config.fallback_offset_hours

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "schedule_config", "fallback_offset_hours"):
        op.add_column(
            "schedule_config",
            sa.Column(
                "fallback_offset_hours",
                sa.Integer(),
                nullable=False,
                server_default="6",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "schedule_config", "fallback_offset_hours"):
        op.drop_column("schedule_config", "fallback_offset_hours")
