"""hypothesis_node_links — pointer table from hypothesis rows to vault notes.

Phase 2 schema-only landing. Routes that consume this table land in Phase 3
together with the LLM bundle assembler. The table itself can be populated
manually now (operator hand-links) or via the indexer's review queue
promote flow once Phase 3 wires it.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hypothesis_node_links",
        sa.Column(
            "hypothesis_id",
            sa.String(length=36),
            sa.ForeignKey("hypothesis.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Vault path is canonical (e.g. "Newsletters/lyn-alden/2026-w19.md").
        # Validated at write time against the vault-indexer service; not FK-enforced
        # because the indexer's cache lives in a separate SQLite DB.
        sa.Column("vault_path", sa.String(length=500), primary_key=True),
        sa.Column(
            "stance",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "added_by",
            sa.String(length=16),
            nullable=False,
            server_default="operator",
        ),
        sa.CheckConstraint(
            "stance IN ('supports', 'challenges', 'context')",
            name="ck_hypothesis_node_links_stance",
        ),
        sa.CheckConstraint(
            "added_by IN ('operator', 'auto')",
            name="ck_hypothesis_node_links_added_by",
        ),
    )
    op.create_index(
        "ix_hypothesis_node_links_vault_path",
        "hypothesis_node_links",
        ["vault_path"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hypothesis_node_links_vault_path",
        table_name="hypothesis_node_links",
    )
    op.drop_table("hypothesis_node_links")
