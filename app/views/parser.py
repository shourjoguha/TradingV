"""Frontmatter parser for the view registry.

Each view lives at ``app/views/registry/<id>.md`` with a YAML frontmatter
block. The parser is intentionally minimal: it splits on ``---`` markers,
runs ``yaml.safe_load`` on the front block, and returns a typed dict.

Boot fails loudly on parse error — the operator sees the broken file
immediately rather than a half-loaded registry at runtime.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

REGISTRY_DIR = Path(__file__).parent / "registry"


class PanelSpec(BaseModel):
    kind: str  # 'ratio' | 'series' | 'spread' | 'hypothesis_filter'
    # Optional fields per panel kind — kept loose so adding new kinds
    # later doesn't require schema changes here.
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    symbol: Optional[str] = None
    sma_days: Optional[int] = None
    threshold: Optional[float] = None
    axis: Optional[str] = None


class ViewSpec(BaseModel):
    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    default_axis: Optional[str] = None
    panels: list[PanelSpec] = Field(default_factory=list)
    body: Optional[str] = None  # markdown body post-frontmatter

    @field_validator("id")
    @classmethod
    def _safe_id(cls, v: str) -> str:
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("id must be alphanumeric + _ -")
        return v


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_md). Both empty if no fm block."""
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    if not isinstance(fm, dict):
        raise ValueError("frontmatter must be a YAML object")
    return fm, body


def parse_file(path: Path) -> ViewSpec:
    raw = path.read_text(encoding="utf-8")
    try:
        fm, body = _split_frontmatter(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"yaml error in {path.name}: {exc}") from exc
    fm["body"] = body or None
    fm.setdefault("id", path.stem)
    try:
        return ViewSpec.model_validate(fm)
    except ValidationError as exc:
        raise ValueError(f"validation error in {path.name}: {exc}") from exc


def load_registry(directory: Optional[Path] = None) -> dict[str, ViewSpec]:
    """Parse every ``*.md`` in the registry directory. Empty dict if missing."""
    d = directory or REGISTRY_DIR
    if not d.is_dir():
        logger.info("view registry dir %s not present — empty registry", d)
        return {}
    out: dict[str, ViewSpec] = {}
    for path in sorted(d.glob("*.md")):
        spec = parse_file(path)
        if spec.id in out:
            raise ValueError(f"duplicate view id: {spec.id}")
        out[spec.id] = spec
    return out


# Singleton populated at app startup. Other modules read from here.
REGISTRY: dict[str, ViewSpec] = {}


def reload() -> dict[str, ViewSpec]:
    """Re-parse the registry directory. Replaces the module-level cache."""
    global REGISTRY
    REGISTRY = load_registry()
    return REGISTRY
