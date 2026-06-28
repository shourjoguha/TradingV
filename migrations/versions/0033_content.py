"""content hierarchy: domains / series / arcs / episodes (video series).

Build-in-public video series feature. Models the editorial tree
(Domain -> Series -> Arc -> Episode) mirroring the platform's own IA, and
binds each episode to a real `source_ref` so the demo-branch verifiability
discipline extends to video.

Verifiability is enforced two ways on `content_episodes`:
  - CHECK status IN ('idea','scripted','filmed','published')
  - CHECK status <> 'published' OR source_ref IS NOT NULL

Design: `.claude/plans/video-series-platform-design.md`.

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_domains",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_content_domains_slug"),
    )

    op.create_table(
        "content_series",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("promise", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["content_domains.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("domain_id", "slug", name="uq_content_series_domain_slug"),
    )

    op.create_table(
        "content_arcs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("theme", sa.Text(), nullable=True),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["series_id"], ["content_series.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("series_id", "slug", name="uq_content_arcs_series_slug"),
    )

    op.create_table(
        "content_episodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("arc_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("hook_text", sa.Text(), nullable=True),
        sa.Column("hook_pattern", sa.String(length=48), nullable=True),
        sa.Column("beat_sheet", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="idea"),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("formats", sa.JSON(), nullable=True),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["arc_id"], ["content_arcs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("arc_id", "slug", name="uq_content_episodes_arc_slug"),
        sa.CheckConstraint(
            "status IN ('idea','scripted','filmed','published')",
            name="ck_content_episodes_status",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR source_ref IS NOT NULL",
            name="ck_content_episodes_published_needs_source",
        ),
    )
    op.create_index(
        "ix_content_episodes_status", "content_episodes", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_content_episodes_status", table_name="content_episodes")
    op.drop_table("content_episodes")
    op.drop_table("content_arcs")
    op.drop_table("content_series")
    op.drop_table("content_domains")
