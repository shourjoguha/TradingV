"""Tests for the operator-authored research-skill loader.

Covers:
  • frontmatter parsing
  • section extraction (Methodology / Example bundle / Example tool call)
  • code-fence stripping for fenced sections
  • mtime-keyed cache invalidation (operator edits propagate)
  • default-skill resolution
  • Anthropic-API few-shot message assembly (with + without tool use)
  • backwards compat — service.ask without a skill folder still works
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.research import skills as _skills


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STRESS_TEST_FRONTMATTER = """\
---
slug: stress-test
title: Stress test
description: Test methodology
tool: propose_invalidator_update
default: true
---

## Methodology
Read the hypothesis. Read the evidence. Output a verdict.
Hard rule: never invent evidence.

## Example bundle

```
HYPOTHESIS
- slug: x
EVIDENCE
- a/b.md (score 0.9): "..."
```

## Example query

Is x still tenable?

## Example verdict

x is weakening.

## Example tool call

```json
{
  "name": "propose_invalidator_update",
  "input": {
    "hypothesis_slug": "x",
    "rationale": "evidence supports change",
    "proposed_invalidator": {"op": "manual", "args": {}},
    "evidence_paths": ["a/b.md"],
    "confidence": 0.6
  }
}
```
"""

VERDICT_ONLY_FRONTMATTER = """\
---
slug: comp-scan
title: Peer comparison
description: One-paragraph peer comparison
default: false
---

## Methodology
You compare a target ticker to its peers. Verdict-only.
"""

INVALID_NO_METHODOLOGY = """\
---
slug: broken
title: Broken
description: Missing required section
---

## Wrong heading
Body without methodology.
"""


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    base = tmp_path / "research"
    base.mkdir()
    _skills.clear_cache()
    return base


def _write(base: Path, name: str, body: str) -> Path:
    p = base / name
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_full_skill_extracts_every_field(skills_dir):
    path = _write(skills_dir, "stress-test.md", STRESS_TEST_FRONTMATTER)
    skill = _skills.parse_skill(path)

    assert skill.slug == "stress-test"
    assert skill.title == "Stress test"
    assert skill.tool == "propose_invalidator_update"
    assert skill.default is True
    assert "never invent evidence" in skill.methodology
    assert "## Methodology" not in skill.methodology  # heading stripped
    assert skill.one_shot_bundle is not None
    assert "HYPOTHESIS" in skill.one_shot_bundle
    assert "```" not in skill.one_shot_bundle  # fence removed
    assert skill.one_shot_query == "Is x still tenable?"
    assert skill.one_shot_verdict == "x is weakening."
    assert isinstance(skill.one_shot_tool_call, dict)
    assert skill.one_shot_tool_call["name"] == "propose_invalidator_update"
    assert skill.has_one_shot is True


def test_parse_verdict_only_skill_has_no_tool(skills_dir):
    path = _write(skills_dir, "comp-scan.md", VERDICT_ONLY_FRONTMATTER)
    skill = _skills.parse_skill(path)

    assert skill.tool is None
    assert skill.default is False
    assert skill.one_shot_bundle is None
    assert skill.one_shot_tool_call is None
    assert skill.has_one_shot is False


def test_parse_skill_missing_methodology_raises(skills_dir):
    path = _write(skills_dir, "broken.md", INVALID_NO_METHODOLOGY)
    with pytest.raises(ValueError, match="Methodology"):
        _skills.parse_skill(path)


# ---------------------------------------------------------------------------
# Cache + lookup
# ---------------------------------------------------------------------------

def test_get_skill_returns_none_when_file_missing(skills_dir):
    assert _skills.get_skill("does-not-exist", skills_dir=skills_dir) is None


def test_get_skill_caches_by_mtime(skills_dir, monkeypatch):
    path = _write(skills_dir, "comp-scan.md", VERDICT_ONLY_FRONTMATTER)
    skill_a = _skills.get_skill("comp-scan", skills_dir=skills_dir)
    skill_b = _skills.get_skill("comp-scan", skills_dir=skills_dir)
    assert skill_a is skill_b  # same instance — cache hit

    # Touch file mtime forward; should re-parse.
    new_mtime = path.stat().st_mtime + 10
    import os
    os.utime(path, (new_mtime, new_mtime))
    skill_c = _skills.get_skill("comp-scan", skills_dir=skills_dir)
    assert skill_c is not skill_a  # cache miss → fresh parse


def test_list_skills_sorted_and_skips_broken(skills_dir, caplog):
    _write(skills_dir, "comp-scan.md", VERDICT_ONLY_FRONTMATTER)
    _write(skills_dir, "stress-test.md", STRESS_TEST_FRONTMATTER)
    _write(skills_dir, "broken.md", INVALID_NO_METHODOLOGY)

    items = _skills.list_skills(skills_dir=skills_dir)
    slugs = [s.slug for s in items]
    assert slugs == ["comp-scan", "stress-test"]
    # Broken skill logged + skipped, not raised.
    assert any("broken.md" in r.message for r in caplog.records)


def test_default_skill_picks_marked_default(skills_dir):
    _write(skills_dir, "comp-scan.md", VERDICT_ONLY_FRONTMATTER)
    _write(skills_dir, "stress-test.md", STRESS_TEST_FRONTMATTER)

    s = _skills.get_default_skill(skills_dir=skills_dir)
    assert s is not None
    assert s.slug == "stress-test"


def test_default_skill_falls_back_to_stress_test_slug(skills_dir):
    # No skill marked default — loader falls back to research-stress-test
    # by slug. With only verdict-only present, returns None.
    _write(skills_dir, "comp-scan.md", VERDICT_ONLY_FRONTMATTER)
    assert _skills.get_default_skill(skills_dir=skills_dir) is None

    # Add a stress-test skill that isn't marked default; loader still finds it.
    _write(
        skills_dir,
        "research-stress-test.md",
        VERDICT_ONLY_FRONTMATTER.replace("comp-scan", "research-stress-test").replace(
            "default: false", "default: false"
        ),
    )
    _skills.clear_cache()
    s = _skills.get_default_skill(skills_dir=skills_dir)
    assert s is not None and s.slug == "research-stress-test"


# ---------------------------------------------------------------------------
# Anthropic-API few-shot adapter
# ---------------------------------------------------------------------------

def _fake_user_builder(query: str, bundle_text: str) -> str:
    return f"BUNDLE\n{bundle_text}\nQ: {query}"


def test_build_one_shot_messages_with_tool_use(skills_dir):
    path = _write(skills_dir, "stress-test.md", STRESS_TEST_FRONTMATTER)
    skill = _skills.parse_skill(path)

    msgs = _skills.build_one_shot_messages(
        skill, user_message_builder=_fake_user_builder
    )
    assert len(msgs) == 3
    # User
    assert msgs[0]["role"] == "user"
    assert "HYPOTHESIS" in msgs[0]["content"]
    assert "Is x still tenable?" in msgs[0]["content"]
    # Assistant: text + tool_use
    assert msgs[1]["role"] == "assistant"
    parts = msgs[1]["content"]
    assert any(p.get("type") == "text" and "weakening" in p["text"] for p in parts)
    tool_use = next(p for p in parts if p.get("type") == "tool_use")
    assert tool_use["name"] == "propose_invalidator_update"
    assert tool_use["input"]["hypothesis_slug"] == "x"
    # Tool result
    assert msgs[2]["role"] == "user"
    assert msgs[2]["content"][0]["type"] == "tool_result"


def test_build_one_shot_messages_verdict_only_skill_returns_empty(skills_dir):
    """A verdict-only skill (no tool, no example sections) gets no
    few-shot anchor — that's fine; the methodology in the system prompt
    is the only steering signal."""
    path = _write(skills_dir, "comp-scan.md", VERDICT_ONLY_FRONTMATTER)
    skill = _skills.parse_skill(path)
    msgs = _skills.build_one_shot_messages(
        skill, user_message_builder=_fake_user_builder
    )
    assert msgs == []


def test_build_one_shot_messages_verdict_only_with_example(skills_dir):
    """A verdict-only skill that DOES have an example bundle + verdict
    should produce a 2-message anchor (no tool_result hop)."""
    body = """\
---
slug: foo
title: Foo
description: foo
---

## Methodology
methodology body

## Example bundle

```
hello
```

## Example query

Is foo?

## Example verdict

foo is good.
"""
    path = _write(skills_dir, "foo.md", body)
    skill = _skills.parse_skill(path)
    msgs = _skills.build_one_shot_messages(
        skill, user_message_builder=_fake_user_builder
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"][0]["text"] == "foo is good."
    # No tool_use because skill has no tool field.
    assert all(p.get("type") != "tool_use" for p in msgs[1]["content"])
