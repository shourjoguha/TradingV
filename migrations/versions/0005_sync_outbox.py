"""sync_outbox

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "sync_outbox" not in existing:
        op.create_table(
            "sync_outbox",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("peer_url", sa.String(length=256), nullable=False),
            sa.Column("symbol", sa.String(length=50), nullable=False),
            sa.Column("asset_class", sa.String(length=16), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column(
                "next_retry_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_sync_outbox_pending",
            "sync_outbox",
            ["completed_at", "next_retry_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_sync_outbox_pending", table_name="sync_outbox")
    op.drop_table("sync_outbox")
