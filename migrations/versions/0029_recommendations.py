"""recommendations table + trades.related_rec_id FK (rx v1.x.1-a).

TradingV becomes the exclusive surface for finance recommendations per
D-045 (storage-routing lock). Schema mirrors the Lovable/Supabase
`recommendations` shape so the laptop's `/rx-finance` slash command can
dual-write without conditional logic per domain.

Key shape notes:
  - `id` is a UUID-as-string (matches existing `trades.id` pattern). We
    don't depend on Postgres `gen_random_uuid()` so dev sqlite stays happy.
  - `owner_user_id` is carried for Supabase-schema parity even though
    TradingV is single-user; server-side fills from env, never trusted
    from client.
  - CHECK constraint pins `domain = 'finance'` — defensive guarantee so
    no cross-domain rows accidentally land here even if a future caller
    is buggy. SQLite enforces CHECK too (so tests catch violations).
  - `facts_json`, `source_refs`, `signals_fired`, `drift_breakdown`,
    `confidence_breakdown` are plain `JSON` for cross-DB compat
    (Postgres stores as JSONB-ish; SQLite as TEXT). Brief specified
    JSONB but we follow the `trades.context_refs` pattern.
  - `trades.related_rec_id` is a nullable FK to recommendations(id) so
    Phase B can wire up the `position_thesis_match` signal end-to-end.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("drift_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("tldr", sa.Text(), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=True),
        sa.Column("rx_md_path", sa.Text(), nullable=True),
        sa.Column("facts_json", sa.JSON(), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("signals_fired", sa.JSON(), nullable=True),
        sa.Column("drift_breakdown", sa.JSON(), nullable=True),
        sa.Column("confidence_breakdown", sa.JSON(), nullable=True),
        sa.Column("acted_disposition", sa.String(64), nullable=True),
        sa.Column(
            "acted_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("subjective_fit_1_5", sa.Integer(), nullable=True),
        sa.Column("next_session_id", sa.String(36), nullable=True),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column(
            "snoozed_until", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "snooze_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "domain = 'finance'", name="ck_recommendations_finance_only"
        ),
        sa.CheckConstraint(
            "status IN ('open','snoozed','acted','dismissed')",
            name="ck_recommendations_status",
        ),
        sa.CheckConstraint(
            "subjective_fit_1_5 IS NULL OR (subjective_fit_1_5 BETWEEN 1 AND 5)",
            name="ck_recommendations_subjective_fit",
        ),
    )
    op.create_index(
        "ix_recommendations_status_created",
        "recommendations",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_recommendations_snoozed_until",
        "recommendations",
        ["snoozed_until"],
        postgresql_where=sa.text("snoozed_until IS NOT NULL"),
    )
    # Every read filters owner_user_id; index keeps single-tenant fast
    # and stays consistent if a future change introduces multi-tenant.
    op.create_index(
        "ix_recommendations_owner_user_id",
        "recommendations",
        ["owner_user_id"],
    )

    # Phase B unlock: link a trade to the rec that prompted it. Nullable
    # FK; ON DELETE SET NULL so we don't lose trades when a rec is purged.
    with op.batch_alter_table("trades") as batch:
        batch.add_column(
            sa.Column("related_rec_id", sa.String(36), nullable=True)
        )
        batch.create_foreign_key(
            "fk_trades_related_rec_id",
            "recommendations",
            ["related_rec_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_trades_related_rec_id",
        "trades",
        ["related_rec_id"],
        postgresql_where=sa.text("related_rec_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendations_owner_user_id", table_name="recommendations"
    )
    op.drop_index("ix_trades_related_rec_id", table_name="trades")
    with op.batch_alter_table("trades") as batch:
        batch.drop_constraint("fk_trades_related_rec_id", type_="foreignkey")
        batch.drop_column("related_rec_id")
    op.drop_index(
        "ix_recommendations_snoozed_until", table_name="recommendations"
    )
    op.drop_index(
        "ix_recommendations_status_created", table_name="recommendations"
    )
    op.drop_table("recommendations")
