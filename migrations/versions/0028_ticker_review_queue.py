"""ticker_review_queue — unknown-ticker review surface (Phase D).

Storage for tickers emitted by Stage 1 (Qwen2-VL) of the video-vision
chart-extraction pipeline that are NOT in the operator's whitelist
(roster + boards + The Street). Persistent until operator resolves
(add to roster / add to board / dismiss).

Laptop-only state — this table is intentionally NOT replicated to
Railway via sync_outbox. The Today strip + Sunday markdown digest
both consume it locally.

Columns:
  - id PK
  - ticker TEXT — uppercase symbol as emitted by Stage 1
  - first_seen_at / last_seen_at TIMESTAMPTZ
  - times_seen int — total cross-video observations
  - channels JSON — array of channel slugs where seen
  - recent_video_ids JSON — last 3 video_ids (where-did-this-come-from trail)
  - recent_caption_snippets JSON — matching 1-line caption snippets
  - status TEXT — pending / added_to_roster / added_to_board / dismissed
  - resolved_at TIMESTAMPTZ NULL
  - resolved_target TEXT NULL — board name when added

Composite index on (status, last_seen_at DESC) for the Today + digest paths.
UNIQUE on ticker so the upsert in service.enqueue_or_bump is cheap.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticker_review_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "times_seen", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("recent_video_ids", sa.JSON(), nullable=False),
        sa.Column("recent_caption_snippets", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_target", sa.Text(), nullable=True),
        # Stamped when a dismissed row is resurrected past the 90d window.
        # Drives the "previously dismissed YYYY-MM-DD" chip on the Today strip.
        sa.Column(
            "previously_dismissed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint("ticker", name="uq_ticker_review_queue_ticker"),
    )
    op.create_index(
        "ix_ticker_review_queue_status_last_seen",
        "ticker_review_queue",
        ["status", sa.text("last_seen_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ticker_review_queue_status_last_seen",
        table_name="ticker_review_queue",
    )
    op.drop_table("ticker_review_queue")
