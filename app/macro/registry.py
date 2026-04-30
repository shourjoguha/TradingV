"""Symbol registry loader. Parses ``registry.yaml`` once at first call
and caches; tests can monkey-patch ``_cache`` to override.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass(frozen=True)
class RegistryEntry:
    symbol: str
    source: str  # 'yfinance' | 'fred'


_REGISTRY_PATH = Path(__file__).parent / "registry.yaml"
_cache: Optional[List[RegistryEntry]] = None


def load_registry(path: Optional[Path] = None) -> List[RegistryEntry]:
    global _cache
    if _cache is not None and path is None:
        return _cache

    p = path or _REGISTRY_PATH
    raw = yaml.safe_load(p.read_text())
    out: List[RegistryEntry] = []
    for item in raw.get("yfinance") or []:
        out.append(RegistryEntry(symbol=item["symbol"], source="yfinance"))
    for item in raw.get("fred") or []:
        # FRED entries use `id` key — normalise to `symbol` field internally.
        out.append(RegistryEntry(symbol=item["id"], source="fred"))

    if path is None:
        _cache = out
    return out


def lookup_source(symbol: str) -> Optional[str]:
    for entry in load_registry():
        if entry.symbol == symbol:
            return entry.source
    return None


def reset_cache() -> None:
    """Test helper — drops the parsed cache so a fresh registry can be loaded."""
    global _cache
    _cache = None
