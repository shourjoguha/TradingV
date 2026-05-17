"""Decay weighting — applied at retrieval, not at storage.

Phase E Commit 2 model:

  - **Evergreen** (Books, fitness/nutrition corpora, or any doc with
    ``evergreen: true`` in frontmatter): weight = 1.0. Never decays.
  - **Sequential ranked-grouped** (finance default): same-author content
    is ranked by ``published_at`` desc within the result set; the ladder
    [1.0, 0.6, 0.45, 0.35, 0.25] applies per rank, with the last rung as
    the floor for rank ≥ len(ladder). Operator intent — when the same
    voice publishes back-to-back, the most recent strongly dominates and
    the margin persists for adjacent ranks; older content collapses to
    the floor.
  - **Off mode** (fitness/nutrition): weight = 1.0 for everything,
    regardless of evergreen flag (no penalty).

Single-author groups still rank: a group of 1 → rank 0 → ladder[0] = 1.0
(no penalty). A group of 2 → ranks 0,1 → 1.0, 0.6 (the t > t-1 step).

When a node has no author (e.g. ``Notes/...`` or ``Topics/...``) it cannot
participate in a ranking group; treat as evergreen for decay purposes —
``Notes`` is operator-authored timeless commentary, ``Topics`` are landing
pages. This preserves the legacy "Class A → timeless" intuition for
unauthored content while letting the new model still penalise rapid
churn from the same source.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from .config import CONFIG


def _derive_group_key(
    node: dict,
    *,
    default_key: str,
    kind_overrides: Optional[dict] = None,
) -> Optional[str]:
    """Pick the grouping key for a single node.

    Order:
      1. If the node's ``kind`` has a ``group_by_path_prefix`` override
         (e.g. ``filing`` → ``Filings/``), the group key is the path segment
         immediately after the prefix. ``Filings/AAPL/2026-q1.md`` → ``AAPL``.
         This catches content like SEC filings that don't carry ``author``.
      2. Else fall back to ``node[default_key]`` (typically ``author``).

    Returns ``None`` when no group can be derived (caller treats as ungrouped).
    """
    if kind_overrides:
        kind = node.get("kind")
        override = kind_overrides.get(kind) if kind else None
        if override and override.get("group_by_path_prefix"):
            prefix = override["group_by_path_prefix"]
            path = node.get("path") or ""
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                head, _, _ = remainder.partition("/")
                if head:
                    return head
            # No path match for this prefix → fall through to default
    val = node.get(default_key)
    return val if val else None


def assign_ranks(
    nodes: Iterable[dict],
    *,
    group_key: str = "author",
    kind_overrides: Optional[dict] = None,
) -> dict[str, int]:
    """Group ``nodes``; within each group, rank 0 = most recent
    ``published_at`` (desc). Returns ``{path: rank}``.

    Grouping key resolution: see :func:`_derive_group_key`. Default = the
    ``group_key`` field on each node (typically ``author``). Per-kind
    overrides let SEC filings group by ticker (path segment) when
    ``author`` is unset.

    Nodes with no derivable group key are skipped (absent from the output
    dict — caller treats as "ungrouped, no decay penalty").

    The function is pure: returns a fresh dict.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        if not node.get("path"):
            continue
        key = _derive_group_key(
            node, default_key=group_key, kind_overrides=kind_overrides,
        )
        if not key:
            continue
        groups[key].append(node)

    ranks: dict[str, int] = {}
    for members in groups.values():
        # Sort by published_at desc. Fall back to path when published_at is
        # None/empty so filings whose ingestion didn't populate the field still
        # rank by their date-prefixed filename (`Filings/AAPL/2026-05-01-...md`
        # sorts naturally newest-first under reverse=True).
        def _sort_key(n: dict) -> tuple[str, str]:
            pub = n.get("published_at") or ""
            path = n.get("path") or ""
            return (pub, path)
        members.sort(key=_sort_key, reverse=True)
        for rank, node in enumerate(members):
            ranks[node["path"]] = rank
    return ranks


def weight_for(node: dict, *, rank: Optional[int] = None) -> float:
    """Return retrieval weight in [0, 1] for a vault_node row dict.

    ``rank`` is the within-group rank (0 = most recent) when the node
    participates in a ranking group; ``None`` when it's ungrouped.

    Decision order:
      1. Evergreen flag (True) → 1.0.
      2. Decay mode = "off" → 1.0.
      3. Rank is None (ungrouped) → 1.0 (no penalty).
      4. Per-kind override on ``node.kind`` → use that ladder + floor.
         A floor of 0.0 is special: combined with the search.py post-filter,
         items past the override's ladder are dropped entirely from results.
      5. Rank in default ladder → ladder[rank].
      6. Rank past default ladder → CONFIG.decay_floor.
    """
    if node.get("evergreen"):
        return 1.0
    if CONFIG.decay_mode == "off":
        return 1.0
    if rank is None:
        return 1.0
    overrides = CONFIG.decay_kind_overrides or {}
    kind = node.get("kind")
    override = overrides.get(kind) if kind else None
    if override and "ladder" in override:
        ladder = tuple(float(v) for v in override["ladder"])
        floor = float(override.get("floor", ladder[-1] if ladder else 0.0))
        return ladder[rank] if rank < len(ladder) else floor
    ladder = CONFIG.decay_ladder
    if rank < len(ladder):
        return ladder[rank]
    return CONFIG.decay_floor
