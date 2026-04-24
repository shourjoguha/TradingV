"""Kronos model registry loader.

Parses `registry.yaml` (hand-authored) into typed `ModelSpec` records.
The registry is the single source of truth for which Kronos models exist
and what they accept. The validator consumes these specs; no other code
should read the YAML directly.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import yaml

_REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    display_name: str
    params_millions: float
    context_length: int
    supported_intervals: Tuple[str, ...]
    supported_asset_classes: Tuple[str, ...]
    required_features: Tuple[str, ...]
    min_history_bars: int
    max_horizon_bars: int
    default_horizon_bars: int
    unverified: bool
    hf_tokenizer: str = ""
    hf_model: str = ""
    notes: str = ""


_lock = threading.Lock()
_cache: Tuple[ModelSpec, ...] | None = None


def _parse(raw: dict) -> Tuple[ModelSpec, ...]:
    models = raw.get("models") or []
    specs: list[ModelSpec] = []
    for entry in models:
        specs.append(
            ModelSpec(
                id=entry["id"],
                display_name=entry["display_name"],
                params_millions=float(entry["params_millions"]),
                context_length=int(entry["context_length"]),
                supported_intervals=tuple(entry["supported_intervals"]),
                supported_asset_classes=tuple(entry["supported_asset_classes"]),
                required_features=tuple(entry["required_features"]),
                min_history_bars=int(entry["min_history_bars"]),
                max_horizon_bars=int(entry["max_horizon_bars"]),
                default_horizon_bars=int(entry["default_horizon_bars"]),
                unverified=bool(entry.get("unverified", False)),
                hf_tokenizer=str(entry.get("hf_tokenizer", "")),
                hf_model=str(entry.get("hf_model", "")),
                notes=str(entry.get("notes", "")),
            )
        )
    ids = [s.id for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate model ids in registry: {ids}")
    return tuple(specs)


def load_models(path: Path | None = None) -> Tuple[ModelSpec, ...]:
    """Load registry. Cached after first call; pass `path` to bypass cache."""
    global _cache
    if path is not None:
        with path.open("r") as fh:
            return _parse(yaml.safe_load(fh))
    with _lock:
        if _cache is None:
            with _REGISTRY_PATH.open("r") as fh:
                _cache = _parse(yaml.safe_load(fh))
        return _cache


def get_model(model_id: str) -> ModelSpec | None:
    for spec in load_models():
        if spec.id == model_id:
            return spec
    return None


def reset_cache() -> None:
    """Test hook — drop the cached registry so next load re-reads the file."""
    global _cache
    with _lock:
        _cache = None
