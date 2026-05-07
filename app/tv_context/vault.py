"""Vault filesystem helpers for TV-context screenshots.

The operator's vault is on the laptop only (per `.claude/principles.md`).
Screenshots land in ``$VAULT_PATH/Sources/tradingview-screenshots/YYYY-MM-DD/``
as ``{ticker}_{HHMMSS}_{nanoid}.png`` plus a sibling ``.md`` sidecar that
the existing vault-indexer picks up automatically (no binary support
required in the indexer).
"""
from __future__ import annotations

import datetime
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

VAULT_ENV = "VAULT_PATH"
DEFAULT_VAULT = Path.home() / "Documents" / "knowledge-vault"
SCREENSHOT_SUBDIR = "Sources/tradingview-screenshots"
SCREENSHOT_NOTE_SUBDIR = "TradingView/Notes"


def vault_root() -> Path | None:
    """Return the configured vault path or ``None`` if disabled.

    On Railway and in tests, ``VAULT_PATH`` is unset → screenshot ingest
    returns 503 instead of writing to a path that doesn't exist.
    """
    raw = os.environ.get(VAULT_ENV)
    if raw is None:
        # Quiet default: only return the default path if it actually
        # exists. Avoids accidental writes on machines where the operator
        # never set up the vault.
        if DEFAULT_VAULT.exists():
            return DEFAULT_VAULT
        return None
    if raw == "":
        return None
    p = Path(raw)
    return p if p.exists() else None


def _short_id(n: int = 8) -> str:
    return secrets.token_urlsafe(n)[:n]


@dataclass
class WriteResult:
    image_path: Path
    sidecar_path: Path
    image_filename: str
    sidecar_filename: str


def write_screenshot(
    *,
    ticker: str,
    image_bytes: bytes,
    operator_note: str = "",
    hypothesis_id: str | None = None,
    captured_at: datetime.datetime | None = None,
) -> WriteResult:
    """Write image + sidecar markdown into vault. Returns paths."""
    root = vault_root()
    if root is None:
        raise RuntimeError("vault_root not available")
    captured_at = captured_at or datetime.datetime.now(datetime.timezone.utc)
    day_dir = root / SCREENSHOT_SUBDIR / captured_at.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{ticker.upper()}_{captured_at.strftime('%H%M%S')}_{_short_id()}"
    image_path = day_dir / f"{stem}.png"
    sidecar_path = day_dir / f"{stem}.md"
    while image_path.exists() or sidecar_path.exists():
        stem = f"{ticker.upper()}_{captured_at.strftime('%H%M%S')}_{_short_id()}"
        image_path = day_dir / f"{stem}.png"
        sidecar_path = day_dir / f"{stem}.md"

    image_path.write_bytes(image_bytes)

    frontmatter_lines = [
        "---",
        f"ticker: {ticker.upper()}",
        f"captured_at: {captured_at.isoformat()}",
        "kind: tradingview-screenshot",
    ]
    if hypothesis_id:
        frontmatter_lines.append(f"hypothesis_id: {hypothesis_id}")
    frontmatter_lines.append("---")
    frontmatter_lines.append("")
    frontmatter_lines.append(f"![[{image_path.name}]]")
    if operator_note:
        frontmatter_lines.append("")
        frontmatter_lines.append(operator_note.strip())
    sidecar_path.write_text("\n".join(frontmatter_lines) + "\n", encoding="utf-8")

    return WriteResult(
        image_path=image_path,
        sidecar_path=sidecar_path,
        image_filename=image_path.name,
        sidecar_filename=sidecar_path.name,
    )


VISION_BLOCK_START = "<!-- vision-summary:start -->"
VISION_BLOCK_END = "<!-- vision-summary:end -->"


def append_vision_block(*, sidecar_path: Path, vision_md: str | None) -> None:
    """Append a vision summary block to the sidecar markdown.

    Idempotent: if a block already exists it's replaced. ``None`` is a
    no-op (vision call skipped or failed).
    """
    if vision_md is None:
        return
    text = sidecar_path.read_text(encoding="utf-8")
    block = f"\n\n{VISION_BLOCK_START}\n{vision_md.strip()}\n{VISION_BLOCK_END}\n"
    if VISION_BLOCK_START in text:
        # Replace existing block.
        before, _, rest = text.partition(VISION_BLOCK_START)
        _, _, after = rest.partition(VISION_BLOCK_END)
        text = before.rstrip() + block + after.lstrip("\n")
    else:
        text = text.rstrip() + block
    sidecar_path.write_text(text, encoding="utf-8")


def append_expired_banner(
    *, sidecar_path: Path, expired_at: datetime.datetime, summary: str
) -> None:
    """Mark sidecar as expired (image dropped) — preserves text + tombstone."""
    if not sidecar_path.exists():
        return
    text = sidecar_path.read_text(encoding="utf-8")
    banner = (
        f"\n\n> Expired {expired_at.strftime('%Y-%m-%d')} — image dropped. "
        f"Tombstone: {summary}\n"
    )
    if "> Expired " in text:
        return  # idempotent
    sidecar_path.write_text(text.rstrip() + banner, encoding="utf-8")
