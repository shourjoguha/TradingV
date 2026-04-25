"""replication extensions: outbox kind/payload + analysis origin

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-25

Adds:
- sync_outbox.kind          (TEXT, default 'ticker')
- sync_outbox.payload_json  (JSON, nullable)
- sync_outbox.symbol/asset_class made nullable (kind='result' rows have neither)
- analysis_jobs.origin      (TEXT, default 'self')
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # --- sync_outbox extensions -------------------------------------------------
    if not _has_column(bind, "sync_outbox", "kind"):
        op.add_column(
            "sync_outbox",
            sa.Column(
                "kind",
                sa.String(length=16),
                nullable=False,
                server_default="ticker",
            ),
        )

    if not _has_column(bind, "sync_outbox", "payload_json"):
        op.add_column(
            "sync_outbox",
            sa.Column("payload_json", sa.JSON(), nullable=True),
        )

    # Relax symbol / asset_class to nullable for kind='result' rows.
    # SQLite cannot ALTER COLUMN — skip; new tables already match the
    # current Base.metadata definition. Postgres does support it.
    if not is_sqlite:
        op.alter_column("sync_outbox", "symbol", existing_type=sa.String(length=50), nullable=True)
        op.alter_column(
            "sync_outbox",
            "asset_class",
            existing_type=sa.String(length=16),
            nullable=True,
        )

    # --- analysis_jobs.origin ---------------------------------------------------
    if not _has_column(bind, "analysis_jobs", "origin"):
        op.add_column(
            "analysis_jobs",
            sa.Column(
                "origin",
                sa.String(length=16),
                nullable=True,
                server_default="self",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if _has_column(bind, "analysis_jobs", "origin"):
        op.drop_column("analysis_jobs", "origin")

    if not is_sqlite:
        op.alter_column(
            "sync_outbox",
            "asset_class",
            existing_type=sa.String(length=16),
            nullable=False,
        )
        op.alter_column(
            "sync_outbox",
            "symbol",
            existing_type=sa.String(length=50),
            nullable=False,
        )

    if _has_column(bind, "sync_outbox", "payload_json"):
        op.drop_column("sync_outbox", "payload_json")
    if _has_column(bind, "sync_outbox", "kind"):
        op.drop_column("sync_outbox", "kind")
