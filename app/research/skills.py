"""Operator-editable research skills.

Reads markdown skill definitions from ``<repo>/skills/research/<slug>.md``,
parses YAML frontmatter + sectioned body, and produces ``ResearchSkill``
objects the service layer can substitute for the hand-coded
``app/research/prompts.py`` constants.

Skill file format::

    ---
    slug: research-stress-test
    title: "Hypothesis stress-test"
    description: "..."
    tool: propose_invalidator_update   # optional; null/missing = verdict-only
    default: true                      # optional; first default seen wins
    ---

    ## Methodology
    [body becomes the system prompt]

    ## Example bundle
    [optional one-shot user-side bundle]

    ## Example query
    [optional one-shot operator query — defaults to a placeholder if absent]

    ## Example verdict
    [optional one-shot assistant text]

    ## Example tool call
    ```json
    {"name": "...", "input": {...}}
    ```

The loader is **lazy**: skill files are read on demand and cached by
file mtime so the operator can edit a skill and the next ``ask`` picks
it up without a backend restart.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import frontmatter

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILLS_DIR = Path(
    os.environ.get(
        "RESEARCH_SKILLS_DIR",
        str(REPO_ROOT / "skills" / "research"),
    )
)


@dataclass(frozen=True)
class ResearchSkill:
    """Parsed skill with everything the service layer needs.

    ``methodology`` becomes Claude's system prompt. The optional ``one_shot_*``
    fields, when all present, get assembled into the same Anthropic-API-shaped
    few-shot messages the original ``prompts.one_shot_messages()`` produced.
    """

    slug: str
    title: str
    description: str
    methodology: str
    tool: Optional[str] = None
    default: bool = False
    one_shot_bundle: Optional[str] = None
    one_shot_query: Optional[str] = None
    one_shot_verdict: Optional[str] = None
    one_shot_tool_call: Optional[dict[str, Any]] = None
    source_path: Optional[str] = None

    @property
    def has_one_shot(self) -> bool:
        return bool(self.one_shot_bundle and self.one_shot_verdict)


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^##\s+(.+?)\s*$")


def _split_sections(body: str) -> dict[str, str]:
    """Return ``{lower-cased H2 heading: body}`` from a markdown blob.

    Body for each heading is everything until the next H2. Trailing whitespace
    trimmed; leading single newline preserved if present after the heading.
    """
    lines = body.splitlines()
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    for line in lines:
        m = _HEADING.match(line)
        if m:
            current = m.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        if current is None:
            continue
        sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


_FENCE = re.compile(r"^```(?:\w+)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Pull out the innermost code-block content if the section is fenced.

    Sections like ``## Example bundle`` and ``## Example tool call`` are
    typically fenced (``​```​ ... ``​```​``). Fall back to
    the raw text when no fence is present.
    """
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        return m.group(1).strip()
    return text


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_skill(path: Path) -> ResearchSkill:
    """Parse a single ``.md`` skill file. Raises ``ValueError`` on missing
    required fields (slug, methodology)."""
    text = path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)
    meta = post.metadata or {}
    sections = _split_sections(post.content)

    slug = meta.get("slug") or path.stem
    title = meta.get("title") or slug
    description = (meta.get("description") or "").strip()
    tool = meta.get("tool") or None
    default = bool(meta.get("default", False))

    methodology = sections.get("methodology", "").strip()
    if not methodology:
        raise ValueError(
            f"skill {path.name!r}: missing required '## Methodology' section"
        )

    one_shot_bundle = _strip_code_fence(sections["example bundle"]) if "example bundle" in sections else None
    one_shot_query = sections["example query"].strip() if "example query" in sections else None
    one_shot_verdict = sections["example verdict"].strip() if "example verdict" in sections else None

    one_shot_tool_call: Optional[dict[str, Any]] = None
    if "example tool call" in sections:
        raw = _strip_code_fence(sections["example tool call"])
        try:
            one_shot_tool_call = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(
                "skill %s: example tool call is not valid JSON (%s); ignoring",
                path.name, e,
            )

    return ResearchSkill(
        slug=slug,
        title=title,
        description=description,
        methodology=methodology,
        tool=tool,
        default=default,
        one_shot_bundle=one_shot_bundle,
        one_shot_query=one_shot_query,
        one_shot_verdict=one_shot_verdict,
        one_shot_tool_call=one_shot_tool_call,
        source_path=str(path),
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    skill: ResearchSkill
    mtime: float


_CACHE: dict[str, _CacheEntry] = {}
_CACHE_LOCK = threading.Lock()


def _resolve_path(slug: str, skills_dir: Path) -> Optional[Path]:
    candidate = skills_dir / f"{slug}.md"
    return candidate if candidate.exists() else None


def get_skill(
    slug: str, *, skills_dir: Optional[Path] = None
) -> Optional[ResearchSkill]:
    """Load + cache a skill by slug. Returns ``None`` if the file doesn't
    exist. Cache key includes mtime so operator edits propagate without
    a restart.
    """
    base = skills_dir or DEFAULT_SKILLS_DIR
    path = _resolve_path(slug, base)
    if path is None:
        return None
    mtime = path.stat().st_mtime
    with _CACHE_LOCK:
        cached = _CACHE.get(slug)
        if cached and cached.mtime == mtime:
            return cached.skill
        skill = parse_skill(path)
        _CACHE[slug] = _CacheEntry(skill=skill, mtime=mtime)
        return skill


def list_skills(*, skills_dir: Optional[Path] = None) -> list[ResearchSkill]:
    """Discover every ``.md`` skill under the skills dir. Returns a list
    sorted by slug. Skills with parse errors are logged + skipped."""
    base = skills_dir or DEFAULT_SKILLS_DIR
    if not base.is_dir():
        return []
    out: list[ResearchSkill] = []
    for path in sorted(base.glob("*.md")):
        try:
            out.append(get_skill(path.stem, skills_dir=base) or parse_skill(path))
        except Exception as e:                              # noqa: BLE001
            logger.warning("skill %s: parse failed (%s); skipping", path.name, e)
    return out


def get_default_skill(
    *, skills_dir: Optional[Path] = None
) -> Optional[ResearchSkill]:
    """Return the first skill marked ``default: true`` in frontmatter,
    or fall back to ``research-stress-test`` if present."""
    for s in list_skills(skills_dir=skills_dir):
        if s.default:
            return s
    return get_skill("research-stress-test", skills_dir=skills_dir)


# ---------------------------------------------------------------------------
# Anthropic-API shape adapters
# ---------------------------------------------------------------------------

def build_one_shot_messages(
    skill: ResearchSkill,
    *,
    user_message_builder: Any,
) -> list[dict[str, Any]]:
    """Render the skill's example as Anthropic-API few-shot messages.

    Caller passes ``user_message_builder = prompts.build_user_message`` so
    we don't re-import inside this module (keeps the import graph clean).

    Returns ``[]`` when the skill has no one-shot example — that's fine,
    the caller should treat it as "no few-shot anchor".
    """
    if not skill.has_one_shot:
        return []

    user_text = user_message_builder(
        query=skill.one_shot_query or "Stress-test this hypothesis.",
        bundle_text=skill.one_shot_bundle or "",
    )
    assistant_content: list[dict[str, Any]] = [
        {"type": "text", "text": skill.one_shot_verdict or ""}
    ]
    tool_use_id = f"toolu_skill_{skill.slug}"
    if skill.one_shot_tool_call and skill.tool:
        assistant_content.append(
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": skill.one_shot_tool_call.get("name") or skill.tool,
                "input": skill.one_shot_tool_call.get("input") or {},
            }
        )
        return [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": "Acknowledged. Ready for the next query.",
                    }
                ],
            },
        ]
    # Verdict-only skill (no tool) — assistant message ends after text.
    return [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_content},
    ]


def clear_cache() -> None:
    """Test helper — drops the parse cache."""
    with _CACHE_LOCK:
        _CACHE.clear()
