"""Walk ``<vault>/Videos/**`` and delete any markdown whose frontmatter
``source_url`` is a YouTube Shorts URL.

Catches both pre-promote drafts (``*.md.draft``) and already-promoted
canonical files (``*.md``). Idempotent — re-running after cleanup finds
zero matches and exits cleanly.

Doesn't touch ``_channel.yaml``: the deleted videos' video_ids stay in
``seen_video_ids`` so the next channel poll won't re-fetch them.

Usage::

    python -m tools.vault_indexer.cleanup_shorts --dry-run    # preview
    python -m tools.vault_indexer.cleanup_shorts              # delete
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import frontmatter

from .config import CONFIG, passes_scope


logger = logging.getLogger(__name__)


def _source_url_for(path: Path) -> Optional[str]:
    """Read the ``source_url`` field from a markdown file's frontmatter.
    Returns ``None`` if the file is unreadable, has no frontmatter, or
    has no ``source_url`` key.
    """
    try:
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return None
    url = post.metadata.get("source_url")
    if not isinstance(url, str):
        return None
    return url


def find_shorts(vault_root: Path) -> list[tuple[Path, str]]:
    """Return [(path, source_url), …] for every Shorts file under
    ``<vault>/Videos/``. Sorted by path for determinism.
    """
    videos_root = vault_root / "Videos"
    if not videos_root.exists():
        return []
    out: list[tuple[Path, str]] = []
    for pattern in ("**/*.md.draft", "**/*.md"):
        for path in videos_root.glob(pattern):
            if not path.is_file():
                continue
            if not passes_scope(str(path.relative_to(vault_root))):
                continue
            url = _source_url_for(path)
            if url and "/shorts/" in url:
                out.append((path, url))
    out.sort(key=lambda pair: str(pair[0]))
    return out


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(
        description="Delete YouTube Shorts files (by frontmatter source_url) "
                    "from <vault>/Videos/. Idempotent."
    )
    ap.add_argument("--vault", default=str(CONFIG.vault_path),
                    help="Vault root. Default: CONFIG.vault_path.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be deleted, but don't unlink.")
    args = ap.parse_args()

    vault_root = Path(args.vault).expanduser()
    if not vault_root.exists():
        logger.error("vault not found: %s", vault_root)
        return 1

    matches = find_shorts(vault_root)
    if not matches:
        print("no shorts found under <vault>/Videos/")
        return 0

    print(f"found {len(matches)} shorts file(s) under {vault_root}/Videos/:")
    deleted = 0
    failed = 0
    for path, url in matches:
        rel = path.relative_to(vault_root)
        if args.dry_run:
            print(f"  WOULD DELETE  {rel}  ←  {url}")
            continue
        try:
            path.unlink()
            print(f"  DELETED       {rel}  ←  {url}")
            deleted += 1
        except OSError as e:
            print(f"  FAILED        {rel}  ←  {e}", file=sys.stderr)
            failed += 1

    if args.dry_run:
        print(f"dry-run: {len(matches)} file(s) matched. Re-run without "
              f"--dry-run to delete.")
    else:
        print(f"done: {deleted} deleted, {failed} failed")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
