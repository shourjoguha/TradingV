"""Deep-result governors (retrieval-depth Phase 8).

Two LLM-judgment features from Phases 3 + 5 introduced new risks:

  * NEW-1 — contradiction-flag alarm fatigue: ``/rx-contradiction-check`` can
    over-flag "conflict"; false positives erode trust in the banner.
  * NEW-2 — web-surface bias: ``/rx-counter-external`` can dress up a single
    low-quality web source as a strong counter.

The fix for both is the same shape: take the trust decision OUT of raw LLM
self-report and put it behind a DETERMINISTIC governor the app applies. The LLM
still does the labeling (stance, source tier); the governor decides — by fixed,
auditable, tunable thresholds — whether that labeling earns a banner / counts
against the thesis. Pure functions, no DB/model, run at ``/v1/rx/deep`` ingest.
"""
from __future__ import annotations

from typing import Optional

# Strength/credibility lattice shared by both governors.
_ORDER = {"none": 0, "thin": 1, "moderate": 2, "strong": 3}
_RANK_TO_NAME = {v: k for k, v in _ORDER.items()}

# Source tier → rank. Primary filings + reputable press are authoritative;
# secondary aggregation is weaker; forums/SEO/unknown are lowest.
_TIER_RANK = {"primary": 3, "reputable": 3, "secondary": 2, "low": 1}


def contradiction_severity(payload: dict) -> dict:
    """Decide whether a contradiction report earns the app's conflict banner.

    NEW-1 guard: the banner fires only on a REAL conflict signal — a
    directly-contradictory source pair, or ≥2 sources contradicting the claim.
    A lone weak contradiction is `medium` (shown, lower prominence); pure
    staleness is `low` (inline note, no banner). This is the alarm-fatigue
    governor: even if the LLM says "contradicts", the banner is gated on
    evidence weight, not the label alone.

    Returns ``{severity, raise_banner, contradicts_count, pair_count,
    rationale}`` where severity ∈ none|low|medium|high.
    """
    pairs = payload.get("contradictory_pairs") or []
    pair_count = len(pairs) if isinstance(pairs, list) else 0

    contradicts = payload.get("contradicts_count")
    if contradicts is None:
        sources = payload.get("sources") or []
        contradicts = sum(
            1 for s in sources
            if isinstance(s, dict) and s.get("stance") == "contradicts"
        )
    contradicts = int(contradicts or 0)
    stale = int(payload.get("stale_count") or 0)

    if pair_count >= 1 or contradicts >= 2:
        sev, banner = "high", True
        why = "direct contradictory pair or >=2 sources contradict the claim"
    elif contradicts == 1:
        sev, banner = "medium", True
        why = "single source contradicts — shown at lower prominence"
    elif stale > 0:
        sev, banner = "low", False
        why = "no contradiction; only stale evidence — inline note, no banner"
    else:
        sev, banner = "none", False
        why = "sources aligned/orthogonal — no conflict"

    return {
        "severity": sev,
        "raise_banner": banner,
        "contradicts_count": contradicts,
        "pair_count": pair_count,
        "rationale": why,
    }


def disconfirmation_credibility(payload: dict) -> dict:
    """Cap an external counter's strength by the quality of its sources.

    NEW-2 guard against web-surface bias: a single source — however confident
    the LLM's self-reported ``strength`` — is capped at ``thin``; ``strong``
    requires >=3 distinct publishers with at least one primary/reputable tier.
    The governor only ever caps DOWNWARD from the self-report (never inflates),
    so an honest ``none`` stays ``none`` and an optimistic single-blog counter
    can't masquerade as decisive.

    Returns ``{credibility, counts_against_thesis, distinct_publishers,
    best_tier, rationale}`` where credibility ∈ none|thin|moderate|strong.
    """
    sources = payload.get("sources") or []
    sources = [s for s in sources if isinstance(s, dict)]
    publishers = {s.get("publisher") for s in sources if s.get("publisher")}
    n_pub = len(publishers)
    tiers = [_TIER_RANK.get((s.get("tier") or "low").lower(), 1) for s in sources]
    best_tier = max(tiers) if tiers else 0

    if n_pub == 0:
        source_cred = "none"
    elif n_pub == 1:
        source_cred = "thin"            # web-surface-bias guard
    elif n_pub >= 3 and best_tier >= 3:
        source_cred = "strong"
    else:
        source_cred = "moderate"

    self_strength = (payload.get("strength") or "none").lower()
    self_rank = _ORDER.get(self_strength, 3)  # unknown self-report = trust sources
    governed_rank = min(_ORDER[source_cred], self_rank)
    credibility = _RANK_TO_NAME[governed_rank]

    counts = credibility in ("moderate", "strong")
    return {
        "credibility": credibility,
        "counts_against_thesis": counts,
        "distinct_publishers": n_pub,
        "best_tier": best_tier,
        "rationale": (
            f"{n_pub} distinct publisher(s), best tier rank {best_tier}; "
            f"capped self-report '{self_strength}' → '{credibility}'"
        ),
    }


def govern(kind: str, payload: object) -> object:
    """Annotate a deep-result payload with its governor verdict at ingest.

    Adds a ``governor`` block to the payload for contradiction/disconfirmation
    kinds; returns other payloads unchanged. Never raises — a non-dict payload
    or a malformed one passes through (the endpoint already validated kind).
    """
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    if kind == "contradiction":
        out["governor"] = contradiction_severity(payload)
    elif kind == "disconfirmation":
        out["governor"] = disconfirmation_credibility(payload)
    return out
