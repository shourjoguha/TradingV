"""rx_deep_results table — out-of-band enrichment store (retrieval-depth Phase 0).

Holds payloads computed in a Claude Code session (deep multi-hop retrieval,
source-contradiction analysis, off-vault disconfirmation) and POSTed back via
POST /v1/rx/deep (ingest-token auth) so the always-on app can surface them
without making any LLM/API calls itself.

Shape notes (mirrors the recommendations conventions):
  - `id` UUID-as-string; no dependency on Postgres gen_random_uuid().
  - `owner_user_id` server-stamped from env, carried for parity.
  - keyed by EITHER `rec_id` OR `query_hash` (≥1 required, enforced at the
    schema + service layer). `rec_id` is deliberately NOT a FK — a deep run
    can precede the rec it informs, and enrichment must never block on
    referential integrity.
  - `kind` CHECK pins the three known payload kinds; SQLite enforces CHECK
    too so tests catch violations.
  - `payload` is plain JSON for cross-DB compat (follows the
    recommendations.facts_json pattern).

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rx_deep_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("rec_id", sa.String(36), nullable=True),
        sa.Column("query_hash", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('deep_retrieval','contradiction','disconfirmation')",
            name="ck_rx_deep_results_kind",
        ),
    )
    op.create_index(
        "ix_rx_deep_results_rec_id",
        "rx_deep_results",
        ["rec_id"],
        postgresql_where=sa.text("rec_id IS NOT NULL"),
    )
    op.create_index(
        "ix_rx_deep_results_query_hash",
        "rx_deep_results",
        ["query_hash"],
        postgresql_where=sa.text("query_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_rx_deep_results_created",
        "rx_deep_results",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_rx_deep_results_created", table_name="rx_deep_results")
    op.drop_index("ix_rx_deep_results_query_hash", table_name="rx_deep_results")
    op.drop_index("ix_rx_deep_results_rec_id", table_name="rx_deep_results")
    op.drop_table("rx_deep_results")
