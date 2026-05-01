"""Runtime config — env-driven."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_VAULT = str(Path.home() / "Documents" / "knowledge-vault")


class Config:
    vault_path: Path = Path(os.environ.get("VAULT_PATH", DEFAULT_VAULT))
    db_path: Path = Path(
        os.environ.get(
            "INDEXER_DB_PATH",
            str(Path(os.environ.get("VAULT_PATH", DEFAULT_VAULT)) / ".indexer" / "cache.db"),
        )
    )
    embedding_model: str = os.environ.get(
        "EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"
    )
    embedding_dim: int = int(os.environ.get("EMBEDDING_DIM", "1024"))
    # bge-large recommends a query-side prefix; passages encoded raw.
    query_prefix: str = os.environ.get(
        "BGE_QUERY_PREFIX",
        "Represent this sentence for searching relevant passages: ",
    )
    anthropic_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    auto_tag_model: str = os.environ.get("AUTO_TAG_MODEL", "claude-haiku-4-5")
    auto_tag_enabled: bool = os.environ.get("AUTO_TAG_ENABLED", "1") == "1"
    # Decay defaults — used when frontmatter horizon_months is missing.
    default_horizon_months: int = int(os.environ.get("DEFAULT_HORIZON_MONTHS", "6"))
    # Folders that hold class-B (time-decayed) content.
    timely_folders: tuple[str, ...] = tuple(
        os.environ.get("TIMELY_FOLDERS", "Newsletters,Videos").split(",")
    )
    chunk_target_tokens: int = int(os.environ.get("CHUNK_TARGET_TOKENS", "600"))
    chunk_overlap_tokens: int = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "80"))


CONFIG = Config()


def is_timely(rel_path: str) -> bool:
    """True if the relative vault path lives under a timely (class-B) folder."""
    head = rel_path.split("/", 1)[0]
    return head in CONFIG.timely_folders
