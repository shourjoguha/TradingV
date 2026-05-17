"""Pydantic shapes for /v1/rx/* endpoints."""
from __future__ import annotations

import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# Acted-disposition vocab — kept loose (free-text up to 64 chars in DB) so
# the generator can evolve labels without a coordinated DB migration. UI
# pins to these three buttons by convention.
ACTED_DISPOSITIONS = ("acted_as_prescribed", "acted_modified", "skipped")


class RecCreate(BaseModel):
    """Ingest payload from the laptop's `/rx-finance` slash command."""

    # `domain` is required + must equal 'finance'. Defensive check on top
    # of the DB CHECK constraint so we return a useful 422 instead of a
    # raw IntegrityError.
    domain: Literal["finance"]
    drift_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[int] = Field(default=None, ge=0, le=100)
    tldr: Optional[str] = None
    body_md: Optional[str] = None
    rx_md_path: Optional[str] = None
    facts_json: Optional[Any] = None
    source_refs: Optional[Any] = None
    signals_fired: Optional[Any] = None
    drift_breakdown: Optional[Any] = None
    confidence_breakdown: Optional[Any] = None
    # Allow the generator to seed `created_at` to align with the markdown
    # frontmatter timestamp. If omitted, server stamps NOW().
    created_at: Optional[datetime.datetime] = None


class RecListItem(BaseModel):
    id: str
    short_id: str
    created_at: datetime.datetime
    age_days: int
    drift_score: Optional[float] = None
    confidence: Optional[int] = None
    status: str
    tldr_short: Optional[str] = None
    acted_disposition: Optional[str] = None
    subjective_fit_1_5: Optional[int] = None
    snoozed_until: Optional[datetime.datetime] = None
    snooze_count: int = 0
    auto_revived: bool = False
    forced_decision: bool = False
    aging: bool = False
    # Phase 2 (tv-context-decision-engine-enrichment): operator-attention
    # axis. Nullable on legacy rows pre-migration. `attention_breakdown`
    # is `{ticker: {kind: count, score: float}}` (JSON-flexible).
    attention_score: Optional[float] = None
    attention_breakdown: Optional[Any] = None


class RecList(BaseModel):
    items: List[RecListItem]
    count: int


class RecRead(BaseModel):
    id: str
    owner_user_id: str
    domain: str
    status: str
    drift_score: Optional[float] = None
    confidence: Optional[int] = None
    tldr: Optional[str] = None
    body_md: Optional[str] = None
    rx_md_path: Optional[str] = None
    facts_json: Optional[Any] = None
    source_refs: Optional[Any] = None
    signals_fired: Optional[Any] = None
    drift_breakdown: Optional[Any] = None
    confidence_breakdown: Optional[Any] = None
    acted_disposition: Optional[str] = None
    acted_at: Optional[datetime.datetime] = None
    subjective_fit_1_5: Optional[int] = None
    next_session_id: Optional[str] = None
    outcome_note: Optional[str] = None
    snoozed_until: Optional[datetime.datetime] = None
    snooze_count: int
    created_at: datetime.datetime
    # Server-computed so the detail page never re-derives the threshold.
    # Kept in sync w/ list endpoint's `forced_decision` flag.
    forced_decision: bool = False
    # Phase 2 attention axis (same shape as list endpoint).
    attention_score: Optional[float] = None
    attention_breakdown: Optional[Any] = None


class DispositionWrite(BaseModel):
    """Operator disposition write (non-snooze path).

    `acted_*` requires `subjective_fit_1_5`; `skipped`/`dismissed` doesn't.
    The brief specifies `subjective_fit` required when status becomes
    'acted' — we enforce here so the UI doesn't have to.
    """

    disposition: Literal[
        "acted_as_prescribed", "acted_modified", "skipped", "dismissed"
    ]
    subjective_fit_1_5: Optional[int] = Field(default=None, ge=1, le=5)
    outcome_note: Optional[str] = Field(default=None, max_length=280)

    @model_validator(mode="after")
    def _check_fit_required_on_acted(self) -> "DispositionWrite":
        if self.disposition in ("acted_as_prescribed", "acted_modified"):
            if self.subjective_fit_1_5 is None:
                raise ValueError(
                    "subjective_fit_1_5 is required when disposition is "
                    "acted_as_prescribed or acted_modified"
                )
        return self


class SnoozeWrite(BaseModel):
    days: int = Field(ge=1, le=7)


class RxLinkHypothesis(BaseModel):
    id: str
    slug: str
    title: str
    status: str


class RxLinkTrade(BaseModel):
    id: str
    ticker: str
    side: str
    qty: float
    entry_price: float
    entry_at: datetime.datetime
    realized_pnl: Optional[float] = None


class RxLinks(BaseModel):
    """Heuristic links from a rec to TradingV-native entities.

    Pre-Phase-I substring heuristic: matches hypotheses + trades whose
    `title` / `ticker` appears in the rec's `tldr|body_md` (case-
    insensitive). Trades also pulled in via the explicit
    `related_rec_id` FK once Phase B trade-capture form is live.
    """

    hypotheses: List[RxLinkHypothesis]
    trades: List[RxLinkTrade]
