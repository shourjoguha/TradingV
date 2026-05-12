"""LLM-driven hub-note drafter — Phase 5 of the multi-domain plan.

Reads an operator-seeded concept list from
``Topics/<domain>/_concepts_to_draft.md`` (one concept per ``- [ ] <name>``
line, same flavour as the ingest queue), retrieves top-K relevant chunks
from the vault_indexer for that domain, calls Claude Haiku to draft a hub
note that summarises the concept and cites the source paths it was given,
validates citations against the actual indexer, writes the draft as
``Topics/<domain>/<concept>.md.draft`` so it surfaces in the per-domain
review queue (``_scan_pending_drafts``), and ticks the source line.

Promote the draft to the canonical ``Topics/<domain>/<concept>.md`` via the
existing review queue ``promote_draft_path`` flow (operator ticks → indexer
applies on /promote).

Usage:

    python -m tools.vault_indexer.jobs.draft_hubs \\
        --domain fitness --indexer http://127.0.0.1:8002 \\
        --max-drafts 5 --top-k 12

Designed to be invoked by launchd on a weekly cadence. Failure modes:
  - Anthropic key missing → exits 0 with stderr note (so the launchd job
    isn't marked failed; the operator just sees nothing happened).
  - Indexer unreachable → exits 0 with note.
  - Per-concept LLM/citation failure → log + continue with the next concept.
  - Existing canonical hub note → skip.
  - Existing pending draft → skip.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import frontmatter

from ..config import CONFIG


CONCEPTS_FILE_NAME = "_concepts_to_draft.md"
TOPICS_DIR_NAME = "Topics"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TOP_K = 12
DEFAULT_MAX_DRAFTS = 5

_TODO_RE = re.compile(r"^\s*- \[ \]\s+(.*\S)\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")


SYSTEM_PROMPT = """You are drafting a concept hub note for an Obsidian-based knowledge vault.

A hub note summarises a single concept (e.g. "RIR (Reps in Reserve)", "Zone 2 cardio")
based on cited source chunks. It is the operator's entry point into deeper material.

Constraints:
- ONLY cite paths that appear verbatim in the user's CHUNKS section. If a fact has no
  supporting chunk, leave it out — do not speculate.
- Cite source chunks with Obsidian-style wikilinks: `[[<path-without-extension>]]`.
  DO NOT include the `.md` extension inside the wikilink target.
- Output the body only — start with a single H1 containing the concept name, then
  3-6 sections (e.g. "Summary", "Key claims", "Open questions", "See also").
- DO NOT include YAML frontmatter at the top. The system adds frontmatter automatically.
- Keep the whole note under 600 words. Hubs are entry points, not encyclopedia articles.
- "See also" lists 2-4 related concepts the operator might want to draft next.
- No explanation, no code fences. Markdown body only."""


def _load_concepts(domain: str, vault_root: Path) -> tuple[Path, list[tuple[int, str, str]]]:
    """Return (concepts_file_path, [(line_idx, raw_line, concept_name), ...])."""
    p = vault_root / TOPICS_DIR_NAME / domain / CONCEPTS_FILE_NAME
    if not p.exists():
        return p, []
    text = p.read_text(encoding="utf-8")
    section = "queue"
    out: list[tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines()):
        m_h = _HEADING_RE.match(line)
        if m_h:
            section = m_h.group(1).lower()
            continue
        if section.startswith("done") or section.startswith("quarantined"):
            continue
        m = _TODO_RE.match(line)
        if not m:
            continue
        rest = m.group(1)
        # Concept name is everything before the first `|` (if any).
        name = rest.split("|", 1)[0].strip()
        if not name:
            continue
        out.append((i, line, name))
    return p, out


def _hub_path_for(domain: str, concept_name: str, vault_root: Path) -> Path:
    return vault_root / TOPICS_DIR_NAME / domain / f"{_slug(concept_name)}.md"


def _draft_path_for(domain: str, concept_name: str, vault_root: Path) -> Path:
    canonical = _hub_path_for(domain, concept_name, vault_root)
    return canonical.with_suffix(canonical.suffix + ".draft")


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "untitled"


def _fetch_chunks(indexer_base: str, query: str, k: int) -> list[dict]:
    qs = urllib.parse.urlencode({"q": query, "k": k})
    req = urllib.request.Request(f"{indexer_base.rstrip('/')}/search?{qs}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return data.get("results") or []


def _format_chunks_for_llm(chunks: list[dict]) -> str:
    """Render chunks as a CHUNKS block the model can cite from."""
    out: list[str] = []
    for i, c in enumerate(chunks, start=1):
        path = c.get("path") or "?"
        section = c.get("section") or ""
        score = c.get("score") or 0
        title = c.get("title") or ""
        text = (c.get("text") or "").strip().replace("\n\n", "\n")
        # Truncate per-chunk text to keep the prompt cache-friendly.
        if len(text) > 1500:
            text = text[:1500] + " […]"
        head = f"[{i}] path={path}"
        if title:
            head += f" | title={title}"
        if section:
            head += f" | section={section}"
        head += f" | score={score:.3f}"
        out.append(head + "\n" + text)
    return "\n\n---\n\n".join(out)


def _validate_citations(
    draft_md: str, vault_root: Path, batch_paths: set[str]
) -> tuple[bool, list[str]]:
    """Reject only PATH-style wikilinks that point at non-existent vault paths.

    Two flavours of wikilink coexist in hub notes:
      - **Path-style** (contains `/`): `[[Books/graham-.../20-margin-of-safety|display]]`.
        These cite source chunks. Validated against the actual vault filesystem.
      - **Concept-style** (no `/`): `[[Margin of safety]]`, `[[Zone 2 cardio]]`.
        These point at sibling hub notes (which may not exist yet — that's
        the whole point of the "See also" section). Tolerated.

    The model often legitimately cites paths it knows from training even if
    that chunk wasn't in this retrieval batch. As long as the path exists
    in the vault, the citation resolves correctly.
    """
    cited_raw = set(re.findall(r"\[\[([^\]\|#]+)", draft_md))

    def _norm(s: str) -> str:
        s = s.strip()
        if s.lower().endswith(".md"):
            s = s[:-3]
        return s.lower()                                       # case-insensitive — APFS default

    # Walk vault once for path-style validation.
    real_stems: set[str] = set()
    for p in vault_root.rglob("*.md"):
        try:
            rel = str(p.relative_to(vault_root))
        except ValueError:
            continue
        if rel.endswith(".md"):
            real_stems.add(rel[:-3].lower())
    real_stems.update(_norm(p) for p in batch_paths)

    bad: list[str] = []
    for c in cited_raw:
        target = _norm(c)
        if "/" not in target:
            # Concept-style — tolerate even if hub doesn't exist yet.
            continue
        if target not in real_stems:
            bad.append(c)                                     # report original
    return (len(bad) == 0, sorted(set(bad)))


def _draft_with_anthropic(
    *, concept: str, chunks: list[dict], model: str, api_key: str
) -> str:
    import anthropic

    chunks_block = _format_chunks_for_llm(chunks)
    user_msg = (
        f"Concept: **{concept}**\n\n"
        f"CHUNKS (use these as the source of truth — cite their `path` via wikilinks):\n\n"
        f"{chunks_block}\n\n"
        f"Draft the hub note now. Output the raw markdown only (frontmatter + body)."
    )

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "".join(parts).strip()


def _rewrite_concepts_file(path: Path, original_lines: list[str], updates: dict[int, str]) -> None:
    if not updates:
        return
    out = []
    for i, line in enumerate(original_lines):
        out.append(updates.get(i, line))
    new_text = "\n".join(out)
    if not new_text.endswith("\n"):
        new_text += "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True,
                    help="Domain slug, e.g. 'fitness', 'nutrition', 'finance'.")
    ap.add_argument("--indexer", required=True,
                    help="Base URL of the vault_indexer for that domain "
                         "(e.g. http://127.0.0.1:8002).")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                    help="How many chunks to retrieve per concept.")
    ap.add_argument("--max-drafts", type=int, default=DEFAULT_MAX_DRAFTS,
                    help="Max concepts to draft per run.")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="Claude model id.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Plan + retrieve chunks; don't call LLM or write drafts.")
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("ANTHROPIC_API_KEY not set — exiting cleanly (no work done).",
              file=sys.stderr)
        return 0

    vault_root = CONFIG.vault_path
    concepts_path, concepts = _load_concepts(args.domain, vault_root)
    if not concepts:
        print(f"no concepts to draft for domain={args.domain} "
              f"(file: {concepts_path}, exists={concepts_path.exists()})",
              file=sys.stderr)
        return 0

    # Indexer reachability probe.
    try:
        urllib.request.urlopen(f"{args.indexer.rstrip('/')}/health", timeout=5)
    except Exception as e:                                      # noqa: BLE001
        print(f"indexer {args.indexer} unreachable ({e}) — exiting.", file=sys.stderr)
        return 0

    drafted = 0
    skipped: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    line_updates: dict[int, str] = {}
    original_lines = concepts_path.read_text(encoding="utf-8").splitlines()

    for line_idx, raw_line, concept in concepts:
        if drafted >= args.max_drafts:
            break

        canonical = _hub_path_for(args.domain, concept, vault_root)
        draft = _draft_path_for(args.domain, concept, vault_root)
        if canonical.exists():
            skipped.append((concept, "canonical exists"))
            continue
        if draft.exists():
            skipped.append((concept, "draft pending review"))
            continue

        try:
            chunks = _fetch_chunks(args.indexer, concept, args.top_k)
        except Exception as e:                                  # noqa: BLE001
            failed.append((concept, f"chunk fetch failed: {e}"))
            continue
        if not chunks:
            skipped.append((concept, "no chunks for concept"))
            continue

        if args.dry_run:
            print(f"[dry-run] {concept}: would draft from {len(chunks)} chunks → {draft.relative_to(vault_root)}")
            drafted += 1
            continue

        try:
            md = _draft_with_anthropic(
                concept=concept, chunks=chunks, model=args.model, api_key=api_key,
            )
        except Exception as e:                                  # noqa: BLE001
            failed.append((concept, f"LLM call failed: {e}"))
            continue

        # Validate citations against the actual vault filesystem (not just
        # the batch we retrieved — model may legitimately cite known paths
        # that weren't in this top-K).
        batch_paths = {c.get("path") for c in chunks if c.get("path")}
        ok, bad_cites = _validate_citations(md, vault_root, batch_paths)
        if not ok:
            failed.append((concept, f"hallucinated citations: {bad_cites[:3]}"))
            continue

        # The system prompt asks the model NOT to include frontmatter, but
        # if it slips one in we strip it cleanly. Then we synthesise
        # canonical frontmatter ourselves.
        body = md.lstrip()
        if body.startswith("---"):
            try:
                post = frontmatter.loads(body)
                body = post.content.lstrip()
            except Exception:                                   # noqa: BLE001
                # Fall through with body as-is.
                pass
        md = (
            f"---\n"
            f"kind: topic\n"
            f"title: \"{concept}\"\n"
            f"domain: {args.domain}\n"
            f"draft: true\n"
            f"tags: []\n"
            f"---\n\n"
            f"{body}\n"
        )

        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(md, encoding="utf-8")
        # Tick the concepts file line.
        line_updates[line_idx] = re.sub(
            r"^\s*- \[ \]\s+", "- [x] ", raw_line, count=1
        )
        drafted += 1
        print(f"drafted → {draft.relative_to(vault_root)}", file=sys.stderr)

    # Persist concepts-file updates atomically.
    _rewrite_concepts_file(concepts_path, original_lines, line_updates)

    summary = {
        "domain": args.domain,
        "drafted": drafted,
        "skipped": skipped,
        "failed": failed,
    }
    print(json.dumps(summary, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
