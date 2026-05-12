"""Alias map loader for wikilink resolution.

Each domain may declare aliases in ``<vault>/_aliases-<domain>.md`` to
collapse multiple wikilink spellings onto one canonical slug. Without this,
PageRank and centrality split signal across spellings of the same concept.

File format (markdown comments allowed):
    # Comments lines starting with `#` ignored
    zone2 → zone-2-cardio
    btc_dominance → btc

Aliases are case-insensitive and slugified (spaces → dashes) on both sides.
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

log = logging.getLogger("vault-indexer.aliases")

_ARROW = re.compile(r"^\s*(.+?)\s*→\s*(.+?)\s*$")


def _slugify(s: str) -> str:
    """Lowercase, strip brackets, spaces → dashes."""
    s = s.strip("[]").strip()
    return s.lower().replace(" ", "-")


def load_alias_map(vault_root: Path, domain: str | None) -> dict[str, str]:
    """Return ``{alias_slug: canonical_slug}`` for the given domain.

    - Missing domain or missing file → empty dict (no aliases).
    - Duplicate alias keys mapping to different canonicals: log WARNING and
      keep the lexicographically-first canonical (deterministic; never
      silent last-wins).
    """
    if not domain:
        return {}
    path = vault_root / f"_aliases-{domain}.md"
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    conflicts: dict[str, set[str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _ARROW.match(line)
        if not m:
            continue
        alias = _slugify(m.group(1))
        canonical = _slugify(m.group(2))
        if alias in result and result[alias] != canonical:
            conflicts.setdefault(alias, {result[alias]}).add(canonical)
            # Deterministic resolution: lex-first canonical wins.
            result[alias] = min(conflicts[alias])
        else:
            result[alias] = canonical
    for alias, candidates in conflicts.items():
        log.warning(
            "alias conflict in %s: %r maps to %s — using %r (lex-first)",
            path.name, alias, sorted(candidates), result[alias],
        )
    return result


def resolve(raw_link: str, alias_map: dict[str, str]) -> str:
    """Resolve a raw wikilink target to its canonical slug.

    Always returns a slug (lowercase, dashed). If no alias matches, returns
    the slugified form of the raw link unchanged.
    """
    slug = _slugify(raw_link)
    return alias_map.get(slug, slug)


def suggest_conflicts(
    observed_targets: set[str],
    alias_map: dict[str, str],
    *,
    min_ratio: float = 0.85,
    max_suggestions: int = 50,
) -> list[tuple[str, str, float]]:
    """Find pairs of observed wikilink targets that look like duplicates.

    Returns ``(target_a, target_b, similarity_ratio)`` for pairs whose stems
    have ``SequenceMatcher.ratio() >= min_ratio`` and which are NOT already
    aliased to each other. Operator triages: add an entry to
    ``_aliases-<domain>.md`` or accept as distinct concepts.

    Uses ``difflib.SequenceMatcher`` (stdlib, no extra deps). For a vault
    of ~thousand targets the O(n²) scan completes in well under a second.
    Gate with ``max_suggestions`` for very large corpora.

    Tuning notes:
    - ``min_ratio=0.85`` flags ``zone2`` ↔ ``zone-2`` (high overlap on
      short strings) but not ``risk-parity`` ↔ ``risk-parity-strategy``
      (which is more often a true distinction).
    - Lower the ratio for more candidates / more false positives.
    """
    # Aliases exist to canonicalize bare slugs (zone2 ↔ zone-2-cardio).
    # Path-shaped wikilinks (containing '/') resolve directly via vault_node
    # lookup and never need aliasing — exclude them from suggestions to keep
    # the operator-facing list signal-rich.
    targets = sorted(t for t in observed_targets if "/" not in t)
    suggestions: list[tuple[str, str, float]] = []
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            if alias_map.get(_slugify(a)) == _slugify(b):
                continue
            if alias_map.get(_slugify(b)) == _slugify(a):
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio >= min_ratio:
                suggestions.append((a, b, ratio))
                if len(suggestions) >= max_suggestions:
                    suggestions.sort(key=lambda t: -t[2])
                    return suggestions
    suggestions.sort(key=lambda t: -t[2])
    return suggestions
