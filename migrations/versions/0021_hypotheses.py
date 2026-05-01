"""hypothesis + hypothesis_evaluation tables — M-2.

Operator-curated trading theses. Each row carries a slug, claim type, axis,
optional parent (sizing dependency) + precondition (existence dependency),
TTL in months, status (active|expired|invalidated|cancelled|manual_closed),
and a JSON invalidator DSL evaluated daily by the lifespan tick. Every
status transition writes a hypothesis_evaluation row for audit + replay.

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hypothesis",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        # enum-as-string so SQLite parity is free
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("axis", sa.String(length=64), nullable=False),
        sa.Column(
            "parent_id",
            sa.String(length=36),
            sa.ForeignKey("hypothesis.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "precondition_id",
            sa.String(length=36),
            sa.ForeignKey("hypothesis.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("primary_metric", sa.String(length=200), nullable=False),
        sa.Column("tracking_signal", sa.String(length=200), nullable=False),
        # JSON not JSONB to keep SQLite parity for tests
        sa.Column("invalidator", sa.JSON(), nullable=False),
        sa.Column("ttl_months", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("body_md", sa.Text(), nullable=True),
        sa.UniqueConstraint("slug", name="uq_hypothesis_slug"),
        sa.CheckConstraint("ttl_months > 0", name="ck_hypothesis_ttl_positive"),
    )
    op.create_index(
        "ix_hypothesis_status_axis", "hypothesis", ["status", "axis"]
    )
    op.create_index(
        "ix_hypothesis_precondition_id", "hypothesis", ["precondition_id"]
    )
    op.create_index("ix_hypothesis_parent_id", "hypothesis", ["parent_id"])
    op.create_index("ix_hypothesis_expires_at", "hypothesis", ["expires_at"])

    op.create_table(
        "hypothesis_evaluation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "hypothesis_id",
            sa.String(length=36),
            sa.ForeignKey("hypothesis.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status_before", sa.String(length=32), nullable=False),
        sa.Column("status_after", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("invalidator_result", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_hypothesis_evaluation_hyp_evaluated",
        "hypothesis_evaluation",
        ["hypothesis_id", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hypothesis_evaluation_hyp_evaluated",
        table_name="hypothesis_evaluation",
    )
    op.drop_table("hypothesis_evaluation")
    op.drop_index("ix_hypothesis_expires_at", table_name="hypothesis")
    op.drop_index("ix_hypothesis_parent_id", table_name="hypothesis")
    op.drop_index("ix_hypothesis_precondition_id", table_name="hypothesis")
    op.drop_index("ix_hypothesis_status_axis", table_name="hypothesis")
    op.drop_table("hypothesis")
