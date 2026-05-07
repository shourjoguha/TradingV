"""tv_context — Phase 1 unified TradingView-context ingest layer.

Adds:
- ``tv_context_items``: polymorphic ingest table for webhook / screenshot /
  note / idea / event entries, with retention + dedupe + tombstone fields.
- ``hypothesis.requires_tv_context``: per-hypothesis flag that toggles the
  research-ask + daily-tick context-needed gate.
- ``hypothesis_tv_context_links``: pointer table from a hypothesis to a
  tv_context_item. Sibling to ``hypothesis_node_links`` (vault-path links)
  rather than an extension — cleaner separation, no nullable composite-PK.
- ``trades.context_refs``: JSON list of tv_context_item ids attributed to
  the trade at close time (Phase 5 enrichment hook).

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tv_context_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("ticker", sa.String(length=50), nullable=True),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="tradingview",
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("tombstone", sa.JSON(), nullable=True),
        sa.Column("vault_path", sa.String(length=500), nullable=True),
        sa.Column(
            "heavy_blob_dropped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("dedupe_key", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('webhook','screenshot','note','idea','event')",
            name="ck_tv_context_items_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active','expired','archived')",
            name="ck_tv_context_items_status",
        ),
    )
    op.create_index(
        "ix_tv_context_items_ticker_captured",
        "tv_context_items",
        ["ticker", "captured_at"],
    )
    op.create_index(
        "ix_tv_context_items_status_expires",
        "tv_context_items",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_tv_context_items_kind_ticker",
        "tv_context_items",
        ["kind", "ticker"],
    )
    op.create_index(
        "ix_tv_context_items_dedupe",
        "tv_context_items",
        ["dedupe_key", "captured_at"],
    )

    op.add_column(
        "hypothesis",
        sa.Column(
            "requires_tv_context",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "hypothesis_tv_context_links",
        sa.Column(
            "hypothesis_id",
            sa.String(length=36),
            sa.ForeignKey("hypothesis.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tv_context_item_id",
            sa.String(length=36),
            sa.ForeignKey("tv_context_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "stance",
            sa.String(length=16),
            nullable=False,
            server_default="context",
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "added_by",
            sa.String(length=16),
            nullable=False,
            server_default="operator",
        ),
        sa.CheckConstraint(
            "stance IN ('supports','challenges','context')",
            name="ck_hyp_tv_ctx_stance",
        ),
    )
    op.create_index(
        "ix_hyp_tv_ctx_links_item",
        "hypothesis_tv_context_links",
        ["tv_context_item_id"],
    )

    op.add_column(
        "trades",
        sa.Column(
            "context_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("trades", "context_refs")
    op.drop_index("ix_hyp_tv_ctx_links_item", table_name="hypothesis_tv_context_links")
    op.drop_table("hypothesis_tv_context_links")
    op.drop_column("hypothesis", "requires_tv_context")
    op.drop_index("ix_tv_context_items_dedupe", table_name="tv_context_items")
    op.drop_index("ix_tv_context_items_kind_ticker", table_name="tv_context_items")
    op.drop_index("ix_tv_context_items_status_expires", table_name="tv_context_items")
    op.drop_index("ix_tv_context_items_ticker_captured", table_name="tv_context_items")
    op.drop_table("tv_context_items")
