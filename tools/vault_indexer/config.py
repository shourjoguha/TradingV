"""Runtime config — env-driven with `_domains.yaml` registry support.

Three-tier precedence for tunables that vary by domain:
    explicit env  >  yaml-derived (from DOMAIN env)  >  hardcoded default

Set `DOMAIN=<slug>` (e.g. `finance`, `fitness`) to pick up domain-specific
defaults from ``<vault_path>/_domains.yaml``. Explicit env vars
(``INCLUDE_FOLDERS``, ``EXCLUDE_FOLDERS``, ``TAXONOMY_FILE``, ``REVIEW_FILE``,
``DEFAULT_HORIZON_MONTHS``, ``AUTO_TAG_ENABLED``) always win — use them as
escape hatches for ad-hoc operation.

Adding a new domain: append an entry to ``_domains.yaml``. Restart affected
services. Finance auto-derives the new EXCLUDE prefix; no other config edits.

Boot-time coherence: ``_log_config_coherence`` emits warnings (never crashes)
when ``DOMAIN`` and ``INDEXER_DB_PATH`` disagree on which domain the operator
intends to configure. Catches "wrong plist, wrong cache" misconfigurations
before they pollute the wrong DB. Soft-warn only — operator may use
``cache-experiment.db`` legitimately.
"""
from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("vault-indexer.config")


# Default decay ladder (Phase E Commit 2). Operator-confirmed:
#   t  >> t-1 ; t-1 > t-2 ; t-2 > t-3 ; floor after rank ≥ 4.
# These are the multiplicative weights applied to (similarity × hybrid score)
# AFTER ranking same-author content by published_at desc.
_DEFAULT_DECAY_LADDER: tuple[float, ...] = (1.0, 0.6, 0.45, 0.35, 0.25)

DEFAULT_VAULT = str(Path.home() / "Documents" / "knowledge-vault")


def _load_domain_registry(vault_path: Path) -> dict:
    """Read ``<vault_path>/_domains.yaml``. Return ``{}`` if missing or invalid.

    Failure is silent so legacy launches without a registry continue to
    work — they just don't get yaml-derived defaults.
    """
    p = vault_path / "_domains.yaml"
    if not p.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:                                       # noqa: BLE001
        return {}
    return data.get("domains") or {}


def _derive_scope_from_registry(
    domain: str, registry: dict
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(include_prefixes, exclude_prefixes)`` for a domain.

    - Legacy entry (``legacy: true``): EXCLUDE = union of ``<Class>/<other-slug>``
      across every non-legacy entry. INCLUDE empty.
    - Typed entry (``classes: [...]``): INCLUDE = union of ``<Class>/<this-slug>``
      from its ``classes`` list. EXCLUDE empty.
    - Unknown domain: ``((), ())``.
    """
    if not domain or domain not in registry:
        return ((), ())
    entry = registry.get(domain) or {}
    if entry.get("legacy"):
        prefixes: list[str] = []
        for other_slug, other_entry in registry.items():
            if other_slug == domain or not other_entry:
                continue
            if other_entry.get("legacy"):
                continue
            for cls in (other_entry.get("classes") or []):
                prefixes.append(f"{cls}/{other_slug}")
        return ((), tuple(prefixes))
    classes = entry.get("classes") or []
    return (tuple(f"{cls}/{domain}" for cls in classes), ())


def _env_csv(name: str) -> tuple[str, ...] | None:
    """Read a comma-separated env var.

    - Unset → ``None`` (caller falls back to derived/default).
    - Set to empty string → ``()`` (caller treats as 'explicitly empty').
    - Set with values → tuple of stripped non-empty values.
    """
    raw = os.environ.get(name)
    if raw is None:
        return None
    return tuple(p.strip() for p in raw.split(",") if p.strip())


class Config:
    def __init__(self) -> None:
        self.vault_path: Path = Path(os.environ.get("VAULT_PATH", DEFAULT_VAULT))
        self.db_path: Path = Path(
            os.environ.get(
                "INDEXER_DB_PATH",
                str(self.vault_path / ".indexer" / "cache.db"),
            )
        )
        self.embedding_model: str = os.environ.get(
            "EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"
        )
        self.embedding_dim: int = int(os.environ.get("EMBEDDING_DIM", "1024"))
        self.query_prefix: str = os.environ.get(
            "BGE_QUERY_PREFIX",
            "Represent this sentence for searching relevant passages: ",
        )
        self.anthropic_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
        self.auto_tag_model: str = os.environ.get("AUTO_TAG_MODEL", "claude-haiku-4-5")
        self.timely_folders: tuple[str, ...] = tuple(
            os.environ.get("TIMELY_FOLDERS", "Newsletters,Videos").split(",")
        )
        self.chunk_target_tokens: int = int(os.environ.get("CHUNK_TARGET_TOKENS", "600"))
        self.chunk_overlap_tokens: int = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "80"))

        # ---- Domain-aware tunables (D-legacy registry) ----
        self.domain: str | None = (os.environ.get("DOMAIN") or "").strip() or None
        self.domain_registry: dict = _load_domain_registry(self.vault_path)
        derived_include, derived_exclude = _derive_scope_from_registry(
            self.domain or "", self.domain_registry
        )
        domain_entry: dict = (
            self.domain_registry.get(self.domain) or {} if self.domain else {}
        )

        # Scope filters: explicit env > yaml-derived > empty.
        env_include = _env_csv("INCLUDE_FOLDERS")
        env_exclude = _env_csv("EXCLUDE_FOLDERS")
        self.include_folders: tuple[str, ...] = (
            env_include if env_include is not None else derived_include
        )
        self.exclude_folders: tuple[str, ...] = (
            env_exclude if env_exclude is not None else derived_exclude
        )

        # Per-domain auxiliary files: explicit env > yaml > hardcoded default.
        self.taxonomy_file: str = (
            os.environ.get("TAXONOMY_FILE")
            or domain_entry.get("taxonomy_file")
            or "_taxonomy.md"
        )
        self.review_file: str = (
            os.environ.get("REVIEW_FILE")
            or domain_entry.get("review_file")
            or "_review-queue.md"
        )

        # default_horizon_months: explicit env > yaml > hardcoded 6.
        env_horizon = os.environ.get("DEFAULT_HORIZON_MONTHS")
        if env_horizon:
            self.default_horizon_months: int = int(env_horizon)
        elif domain_entry.get("default_horizon_months") is not None:
            self.default_horizon_months = int(domain_entry["default_horizon_months"])
        else:
            self.default_horizon_months = 6

        # auto_tag_enabled: explicit env > yaml > hardcoded True.
        env_at = os.environ.get("AUTO_TAG_ENABLED")
        if env_at is not None:
            self.auto_tag_enabled: bool = env_at == "1"
        elif "auto_tag_enabled" in domain_entry:
            self.auto_tag_enabled = bool(domain_entry["auto_tag_enabled"])
        else:
            self.auto_tag_enabled = True

        # ---- Graph layer tunables (Phase 0+) ----
        # All graph features are gated by graph_enabled. Default ON because
        # the hybrid scorer applies a min_edges floor before re-ranking, so
        # cold-start corpora behave identically to the pre-graph baseline.
        graph_entry: dict = (domain_entry.get("graph") or {}) if domain_entry else {}

        env_graph = os.environ.get("GRAPH_ENABLED")
        if env_graph is not None:
            self.graph_enabled: bool = env_graph == "1"
        elif "enabled" in graph_entry:
            self.graph_enabled = bool(graph_entry["enabled"])
        else:
            self.graph_enabled = True

        # Hybrid scoring weights: final = α·(sim·decay) + β·citation_rank + γ·centrality + recency
        # α dominant (0.6) keeps semantic relevance primary; β > γ because
        # citation edges are deliberate (hub authorship) vs mechanically derived.
        weights_entry = graph_entry.get("hybrid_weights") or {}
        self.graph_alpha: float = float(
            os.environ.get("GRAPH_ALPHA") or weights_entry.get("alpha") or 0.6
        )
        self.graph_beta: float = float(
            os.environ.get("GRAPH_BETA") or weights_entry.get("beta") or 0.25
        )
        self.graph_gamma: float = float(
            os.environ.get("GRAPH_GAMMA") or weights_entry.get("gamma") or 0.15
        )

        # Graceful-degradation floor: below this edge count, hybrid scoring is
        # a no-op (results identical to pre-graph baseline). Prevents noise on
        # near-empty graphs (cold start / sparse domains).
        self.graph_min_edges: int = int(
            os.environ.get("GRAPH_MIN_EDGES")
            or graph_entry.get("min_edges_for_hybrid")
            or 10
        )

        # Recency boost: small additive score lift for recently-indexed nodes
        # so new high-quality content can compete with well-cited older content
        # (mitigates PageRank rich-get-richer bias).
        self.recency_boost_days: int = int(
            os.environ.get("RECENCY_BOOST_DAYS")
            or graph_entry.get("recency_boost_days")
            or 30
        )
        self.recency_boost_amount: float = float(
            os.environ.get("RECENCY_BOOST_AMOUNT")
            or graph_entry.get("recency_boost_amount")
            or 0.05
        )

        # Recompute debounce: collapse a burst of /reload calls into one
        # background recompute (avoids 10x recompute when ticking 10 review
        # queue items in quick succession).
        self.graph_debounce_seconds: float = float(
            os.environ.get("GRAPH_DEBOUNCE_SECONDS")
            or graph_entry.get("debounce_seconds")
            or 30.0
        )

        # ---- Decay model (Phase E Commit 2) ----
        # `mode`:
        #   - "ranked_grouped" (finance default): same-author content ranked
        #     by published_at desc; ladder weights applied per rank; floor
        #     applies at rank ≥ len(ladder).
        #   - "off" (fitness/nutrition default): all weights = 1.0; evergreen
        #     flag still honoured for completeness but has no effect.
        # `evergreen_paths`: list of glob patterns. Path-glob default for
        # `vault_node.evergreen` when frontmatter doesn't specify one.
        decay_entry: dict = (
            (domain_entry.get("decay") or {}) if domain_entry else {}
        )
        env_decay_mode = os.environ.get("DECAY_MODE")
        self.decay_mode: str = (
            (env_decay_mode or decay_entry.get("mode") or "off").strip().lower()
        )
        env_decay_ladder = _env_csv("DECAY_LADDER")
        if env_decay_ladder is not None:
            try:
                self.decay_ladder: tuple[float, ...] = tuple(
                    float(v) for v in env_decay_ladder
                )
            except ValueError:
                logger.warning(
                    "DECAY_LADDER=%r is not numeric; falling back to default",
                    env_decay_ladder,
                )
                self.decay_ladder = _DEFAULT_DECAY_LADDER
        elif decay_entry.get("ladder"):
            self.decay_ladder = tuple(float(v) for v in decay_entry["ladder"])
        else:
            self.decay_ladder = _DEFAULT_DECAY_LADDER
        env_decay_floor = os.environ.get("DECAY_FLOOR")
        if env_decay_floor:
            self.decay_floor: float = float(env_decay_floor)
        elif "floor" in decay_entry:
            self.decay_floor = float(decay_entry["floor"])
        else:
            # Default = last rung of ladder. Operator intent: rank ≥ len(ladder)
            # collapses to the floor weight.
            self.decay_floor = (
                self.decay_ladder[-1] if self.decay_ladder else 0.25
            )
        env_decay_group = os.environ.get("DECAY_GROUP_KEY")
        self.decay_group_key: str = (
            env_decay_group or decay_entry.get("group_key") or "author"
        ).strip()
        env_evergreen = _env_csv("DECAY_EVERGREEN_PATHS")
        if env_evergreen is not None:
            self.evergreen_globs: tuple[str, ...] = env_evergreen
        else:
            self.evergreen_globs = tuple(decay_entry.get("evergreen_paths") or ())

        # Per-kind overrides — for content that doesn't carry `author` and
        # needs a different grouping signal (e.g. SEC filings group by ticker
        # via the Filings/<TICKER>/ path prefix). Shape:
        #   {
        #     "filing": {
        #       "group_by_path_prefix": "Filings/",  # group key = segment after prefix
        #       "ladder": [1.0, 0.6],
        #       "floor": 0.0,  # 0 → effectively dropped by search.py post-filter
        #     }
        #   }
        # ``floor: 0.0`` is special: search.py filters those rows out so the
        # corpus carries only the top-N filings per ticker (N = len(ladder)).
        self.decay_kind_overrides: dict = (
            decay_entry.get("kind_overrides") or {}
        )

        # ---- Lexical / RRF (Phase E Commit 4) ----
        # Lexical signal is a second retrieval leg (FTS5 BM25) merged with
        # the vector signal via Reciprocal Rank Fusion. Per-domain weights:
        # finance balances ~2:1 vector:lexical because operator queries often
        # have lexical anchors (ticker, "earnings", proper nouns). Fitness /
        # nutrition bias heavily toward vector because (a) corpora are small
        # so lexical false-positives outweigh true matches; (b) operator
        # explicitly requested vector/graph dominance there.
        lexical_entry: dict = (
            (domain_entry.get("lexical") or {}) if domain_entry else {}
        )
        env_lexical_enabled = os.environ.get("LEXICAL_ENABLED")
        if env_lexical_enabled is not None:
            self.lexical_enabled: bool = env_lexical_enabled == "1"
        elif "enabled" in lexical_entry:
            self.lexical_enabled = bool(lexical_entry["enabled"])
        else:
            self.lexical_enabled = True
        env_vw = os.environ.get("LEXICAL_VECTOR_WEIGHT")
        self.lexical_vector_weight: float = float(
            env_vw or lexical_entry.get("vector_weight") or 1.0
        )
        env_lw = os.environ.get("LEXICAL_LEXICAL_WEIGHT")
        self.lexical_lexical_weight: float = float(
            env_lw or lexical_entry.get("lexical_weight") or 0.5
        )
        env_min_tokens = os.environ.get("LEXICAL_MIN_TOKENS")
        # Skip the lexical leg on single-word queries (too noisy; one term
        # matches half the corpus). Operator-typed queries are usually
        # 3-6 tokens.
        self.lexical_min_tokens: int = int(
            env_min_tokens or lexical_entry.get("min_tokens") or 2
        )

    def is_evergreen_path(self, rel_path: str) -> Optional[bool]:
        """Return ``True`` if ``rel_path`` matches any configured evergreen
        glob, ``False`` if globs are configured and none match, and ``None``
        when no globs are configured (caller should treat as "unclassified").

        Used by ``vault.parse_file`` to derive the path-glob default for
        ``VaultNode.evergreen`` when the doc's frontmatter doesn't specify.
        """
        if not self.evergreen_globs:
            return None
        norm = rel_path.replace("\\", "/")
        for pattern in self.evergreen_globs:
            if fnmatch.fnmatch(norm, pattern):
                return True
        return False


def _log_config_coherence(cfg: "Config") -> None:
    """Emit warnings when DOMAIN and INDEXER_DB_PATH disagree.

    Two failure modes caught:
      1. DOMAIN=X but DB filename != ``cache-X.db`` and != legacy ``cache.db``
         → likely wrong plist or wrong env (X intended, but writing somewhere
         else). Warn so the operator sees it in the launchd log.
      2. DOMAIN unset but DB filename matches the ``cache-<slug>.db`` pattern
         → operator probably forgot to set DOMAIN; indexer will fall through
         to single-vault legacy scope (full vault, no exclusion). Warn.

    Both are soft warnings (logger.warning). The indexer continues booting —
    there are valid edge cases (operator running ``cache-experiment.db`` for
    a one-off, or running pre-registry installs with no DOMAIN). The goal is
    visibility, not gating.
    """
    db_name = cfg.db_path.name  # e.g. "cache-finance.db"
    domain = cfg.domain  # str or None

    # Case 1: DOMAIN set, DB name doesn't follow the convention.
    if domain:
        expected = f"cache-{domain}.db"
        if db_name not in (expected, "cache.db"):
            logger.warning(
                "config coherence: DOMAIN=%r but INDEXER_DB_PATH points at "
                "%r (expected %r or legacy %r). Cache may be misconfigured; "
                "verify the launchd plist or env.",
                domain, db_name, expected, "cache.db",
            )
        return

    # Case 2: DOMAIN unset, DB name looks domain-specific.
    if db_name.startswith("cache-") and db_name.endswith(".db"):
        inferred = db_name[len("cache-"):-len(".db")]
        logger.warning(
            "config coherence: INDEXER_DB_PATH=%r looks domain-specific "
            "(implied domain=%r) but DOMAIN env is unset. Indexer will use "
            "single-vault legacy scope (no exclusion). Set DOMAIN=%s to pick "
            "up the registry-derived scope.",
            db_name, inferred, inferred,
        )


CONFIG = Config()
_log_config_coherence(CONFIG)


def passes_scope(rel_path: str) -> bool:
    """Apply INCLUDE_FOLDERS / EXCLUDE_FOLDERS prefix filters.

    - If exclude matches → drop.
    - If include is non-empty and no include matches → drop.
    - Otherwise keep.
    """
    norm = rel_path.replace("\\", "/")
    for prefix in CONFIG.exclude_folders:
        if norm == prefix or norm.startswith(prefix.rstrip("/") + "/"):
            return False
    if CONFIG.include_folders:
        for prefix in CONFIG.include_folders:
            if norm == prefix or norm.startswith(prefix.rstrip("/") + "/"):
                return True
        return False
    return True


def is_timely(rel_path: str) -> bool:
    """True if the relative vault path lives under a timely (class-B) folder."""
    head = rel_path.split("/", 1)[0]
    return head in CONFIG.timely_folders
