"""agent_decisions table — Agents lane (TradingAgents) storage.

Independent of Kronos' prediction_points/opportunities: the multi-agent engine
runs side-by-side and writes only here. Idempotent on
(ticker, made_on, engine_version).

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("made_on", sa.Date(), nullable=False),
        sa.Column(
            "engine",
            sa.String(length=64),
            nullable=False,
            server_default="tradingagents",
        ),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("stance", sa.String(length=8), nullable=False),  # BUY | SELL | HOLD
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rationale_md", sa.Text(), nullable=True),
        sa.Column("transcript_ref", sa.String(length=512), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "ticker", "made_on", "engine_version", name="uq_agent_decision_ticker_day"
        ),
    )
    op.create_index("ix_agent_decisions_ticker", "agent_decisions", ["ticker"])
    op.create_index("ix_agent_decisions_made_on", "agent_decisions", ["made_on"])


def downgrade() -> None:
    op.drop_index("ix_agent_decisions_made_on", table_name="agent_decisions")
    op.drop_index("ix_agent_decisions_ticker", table_name="agent_decisions")
    op.drop_table("agent_decisions")
