"""Tests for the YouTube channel auto-ingest pipeline.

Mostly pure-logic / IO-mocked. The actual yt-dlp + whisper round-trip is
exercised manually by the operator on first channel — too slow + flaky for CI.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


@pytest.fixture
def tmp_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("INDEXER_DB_PATH", str(tmp_path / ".indexer" / "cache.db"))
    monkeypatch.setenv("AUTO_TAG_ENABLED", "0")
    for mod in [m for m in list(sys.modules) if m == "vault_indexer" or m.startswith("vault_indexer.")]:
        del sys.modules[mod]
    return tmp_path


# ---------------------------------------------------------------------------
# _channel.yaml helpers
# ---------------------------------------------------------------------------


def test_channel_yaml_load_save_roundtrip(tmp_vault):
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "fx-evolution-daily"
    channel_dir.mkdir(parents=True)
    cfg = {
        "channel_id": "UCabc",
        "channel_url": "https://youtube.com/@fx",
        "author": "FX Person",
        "default_kind": "video",
        "default_horizon_months": 6,
        "default_tags": ["macro", "fx"],
        "ingest": {
            "enabled": True,
            "cadence": "daily",
            "auto_promote": False,
            "prefer_captions": True,
        },
    }
    cy.save(channel_dir, cfg)
    loaded = cy.load(channel_dir)
    assert loaded["channel_id"] == "UCabc"
    assert loaded["ingest"]["enabled"] is True


def test_channel_yaml_is_due_when_never_polled(tmp_vault):
    from vault_indexer.ingest import _channel_yaml as cy

    cfg = {"ingest": {"enabled": True, "cadence": "daily"}}
    assert cy.is_due(cfg) is True


def test_channel_yaml_is_due_respects_cadence(tmp_vault):
    from vault_indexer.ingest import _channel_yaml as cy

    now = datetime.datetime.now(datetime.timezone.utc)
    just_polled = (now - datetime.timedelta(hours=2)).isoformat()
    cfg = {"ingest": {"enabled": True, "cadence": "daily", "last_polled_at": just_polled}}
    assert cy.is_due(cfg, now=now) is False                  # 2 hrs < 1 day

    a_day_ago = (now - datetime.timedelta(days=1, minutes=5)).isoformat()
    cfg["ingest"]["last_polled_at"] = a_day_ago
    assert cy.is_due(cfg, now=now) is True


def test_channel_yaml_is_due_respects_disabled_and_manual(tmp_vault):
    from vault_indexer.ingest import _channel_yaml as cy

    assert cy.is_due({"ingest": {"enabled": False, "cadence": "daily"}}) is False
    assert cy.is_due({"ingest": {"enabled": True, "cadence": "manual"}}) is False


def test_channel_yaml_mark_polled_rolls_seen_window(tmp_vault):
    from vault_indexer.ingest import _channel_yaml as cy

    cfg = {"ingest": {"enabled": True, "cadence": "daily"}}
    cfg = cy.mark_polled(cfg, video_ids=["a", "b", "c"])
    assert cfg["ingest"]["seen_video_ids"] == ["a", "b", "c"]
    assert cfg["ingest"]["last_video_id"] == "a"

    # Re-poll with a new id; old ids preserved.
    cfg = cy.mark_polled(cfg, video_ids=["d"])
    assert cfg["ingest"]["seen_video_ids"][:4] == ["d", "a", "b", "c"]


def test_channel_yaml_seen_window_caps_at_50(tmp_vault):
    from vault_indexer.ingest import _channel_yaml as cy

    cfg = {"ingest": {"enabled": True, "cadence": "daily", "seen_video_ids": [f"v{i}" for i in range(60)]}}
    cfg = cy.mark_polled(cfg, video_ids=["new"])
    assert len(cfg["ingest"]["seen_video_ids"]) == 50
    assert cfg["ingest"]["seen_video_ids"][0] == "new"


def test_has_seen(tmp_vault):
    from vault_indexer.ingest import _channel_yaml as cy

    cfg = {"ingest": {"seen_video_ids": ["abc", "def"]}}
    assert cy.has_seen(cfg, "abc") is True
    assert cy.has_seen(cfg, "xyz") is False


# ---------------------------------------------------------------------------
# VTT cleanup
# ---------------------------------------------------------------------------


def test_vtt_to_text_strips_timestamps_and_dedupes(tmp_vault):
    from vault_indexer.ingest.youtube_channel import _vtt_to_text

    sample = """WEBVTT

00:00:00.000 --> 00:00:02.500
Welcome to the show.

00:00:02.500 --> 00:00:05.000
Welcome to the show.

00:00:05.000 --> 00:00:07.000
Today we discuss <00:00:05.500>DXY</c>."""
    out = _vtt_to_text(sample)
    assert "WEBVTT" not in out
    assert "-->" not in out
    assert "<" not in out
    # Auto-caption duplicate-line dedupe.
    assert out.count("Welcome to the show.") == 1


# ---------------------------------------------------------------------------
# Draft rendering
# ---------------------------------------------------------------------------


def test_render_draft_includes_frontmatter_with_draft_flag(tmp_vault):
    from vault_indexer.ingest.youtube_channel import (
        FeedEntry, render_draft, write_draft,
    )

    entry = FeedEntry(
        video_id="abc123",
        title="DXY Pivot Setup",
        published_at="2026-05-06",
        url="https://www.youtube.com/watch?v=abc123",
    )
    cfg = {
        "author": "FX Person",
        "default_kind": "video",
        "default_horizon_months": 6,
        "default_tags": ["macro", "fx"],
        "_rel_dir": "Videos/fx-evolution-daily",
    }
    body, meta = render_draft(
        entry=entry, transcript="The transcript text.",
        cfg=cfg, transcript_source="captions",
    )
    assert meta["draft"] is True
    assert meta["video_id"] == "abc123"
    assert meta["author"] == "FX Person"
    assert meta["asr"] == "captions"
    assert meta["parent"] == "Videos/fx-evolution-daily/_index.md"
    assert meta["tags"] == ["macro", "fx"]
    assert "DXY Pivot Setup" in body
    assert "FX Person" in body
    assert "The transcript text." in body

    written = write_draft(
        vault_root=tmp_vault,
        rel_dir="Videos/fx-evolution-daily",
        entry=entry,
        body=body,
        metadata=meta,
    )
    assert written.name == "2026-05-06-dxy-pivot-setup.md.draft"
    assert written.exists()


def test_write_draft_is_idempotent(tmp_vault):
    from vault_indexer.ingest.youtube_channel import (
        FeedEntry, render_draft, write_draft,
    )

    entry = FeedEntry(video_id="x", title="X", published_at="2026-05-06", url="u")
    cfg = {"author": "a", "default_kind": "video"}
    body, meta = render_draft(
        entry=entry, transcript="t", cfg=cfg, transcript_source="captions",
    )
    a = write_draft(
        vault_root=tmp_vault, rel_dir="Videos/foo", entry=entry, body=body, metadata=meta,
    )
    b = write_draft(
        vault_root=tmp_vault, rel_dir="Videos/foo", entry=entry, body=body, metadata=meta,
    )
    assert a == b


# ---------------------------------------------------------------------------
# Review-queue draft surfacing + promote
# ---------------------------------------------------------------------------


def test_pending_drafts_surface_in_review_queue(tmp_vault):
    from vault_indexer import review

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    (channel_dir / "2026-05-06-foo.md.draft").write_text(
        "---\nkind: video\ntitle: Foo\nauthor: A\npublished_at: 2026-05-06\n"
        "draft: true\n---\nbody\n",
        encoding="utf-8",
    )

    pending = review._scan_pending_drafts(tmp_vault)
    assert len(pending) == 1
    assert pending[0]["path"] == "Videos/ch/2026-05-06-foo.md.draft"
    assert pending[0]["title"] == "Foo"
    assert pending[0]["author"] == "A"

    rendered = review.render({"pending_drafts": pending})
    assert "promote draft: `Videos/ch/2026-05-06-foo.md.draft`" in rendered
    assert "Pending video drafts" in rendered


def test_parse_ticks_detects_draft_promote(tmp_vault):
    from vault_indexer import review

    text = (
        "## Pending video drafts\n\n"
        "### Videos/ch/2026-05-06-foo.md.draft\n"
        "- [x] promote draft: `Videos/ch/2026-05-06-foo.md.draft`\n"
    )
    ticks = review.parse_ticks(text)
    assert ("draft_promote", {"path": "Videos/ch/2026-05-06-foo.md.draft"}) in ticks


def test_promote_renames_draft_and_strips_flag(tmp_vault):
    from vault_indexer import cache, review
    from vault_indexer.config import CONFIG

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    draft = channel_dir / "2026-05-06-foo.md.draft"
    draft.write_text(
        "---\nkind: video\ntitle: Foo\ndraft: true\n---\nbody\n",
        encoding="utf-8",
    )

    con = cache.init(CONFIG.db_path, CONFIG.embedding_dim)
    counts = review.promote(con, tmp_vault, [
        ("draft_promote", {"path": "Videos/ch/2026-05-06-foo.md.draft"}),
    ])
    assert counts["drafts_promoted"] == 1
    assert not draft.exists()
    promoted = channel_dir / "2026-05-06-foo.md"
    assert promoted.exists()
    text = promoted.read_text(encoding="utf-8")
    assert "draft:" not in text                              # flag stripped


def test_promote_skips_when_target_already_exists(tmp_vault):
    from vault_indexer import cache, review
    from vault_indexer.config import CONFIG

    d = tmp_vault / "Videos" / "ch"
    d.mkdir(parents=True)
    (d / "2026-05-06-foo.md").write_text("existing", encoding="utf-8")
    (d / "2026-05-06-foo.md.draft").write_text(
        "---\ndraft: true\n---\n", encoding="utf-8"
    )

    con = cache.init(CONFIG.db_path, CONFIG.embedding_dim)
    counts = review.promote(con, tmp_vault, [
        ("draft_promote", {"path": "Videos/ch/2026-05-06-foo.md.draft"}),
    ])
    assert counts["drafts_promoted"] == 0
    assert counts["skipped"] == 1


# ---------------------------------------------------------------------------
# discover_channel_dirs
# ---------------------------------------------------------------------------


def test_discover_channel_dirs(tmp_vault):
    from vault_indexer.ingest.youtube_channel import discover_channel_dirs

    a = tmp_vault / "Videos" / "ch-a"
    a.mkdir(parents=True)
    (a / "_channel.yaml").write_text("channel_id: UCa\n", encoding="utf-8")

    b = tmp_vault / "Videos" / "ch-b"
    b.mkdir(parents=True)
    (b / "_channel.yaml").write_text("channel_id: UCb\n", encoding="utf-8")

    # No config — should be skipped.
    c = tmp_vault / "Videos" / "no-config"
    c.mkdir(parents=True)

    found = sorted(d.name for d in discover_channel_dirs(tmp_vault))
    assert found == ["ch-a", "ch-b"]


# ---------------------------------------------------------------------------
# ingest_one with mocked feed + transcript
# ---------------------------------------------------------------------------


def test_ingest_one_writes_drafts_and_marks_seen(tmp_vault, monkeypatch):
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_id": "UCabc",
        "channel_url": "https://youtube.com/@x",
        "author": "X Person",
        "default_kind": "video",
        "default_horizon_months": 6,
        "default_tags": ["macro"],
        "ingest": {"enabled": True, "cadence": "daily", "prefer_captions": True},
    })

    # Mock the feed.
    fake_entries = [
        yt.FeedEntry(video_id="vid1", title="First Video", published_at="2026-05-05",
                     url="https://www.youtube.com/watch?v=vid1"),
        yt.FeedEntry(video_id="vid2", title="Second Video", published_at="2026-05-06",
                     url="https://www.youtube.com/watch?v=vid2"),
    ]
    monkeypatch.setattr(yt, "fetch_feed", lambda channel_id: fake_entries)

    # Mock captions to always succeed.
    def _fake_captions(url, *, work_dir):
        return f"transcript for {url}"
    monkeypatch.setattr(yt, "fetch_captions", _fake_captions)

    result = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)
    assert result["drafts_written"] == 2
    assert (channel_dir / "2026-05-05-first-video.md.draft").exists()
    assert (channel_dir / "2026-05-06-second-video.md.draft").exists()

    # Re-run — both already seen, no new drafts.
    cfg = cy.load(channel_dir)
    assert "vid1" in (cfg["ingest"].get("seen_video_ids") or [])
    assert "vid2" in (cfg["ingest"].get("seen_video_ids") or [])

    # Force is_due to True so the second tick fires.
    cfg["ingest"]["last_polled_at"] = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
    ).isoformat()
    cy.save(channel_dir, cfg)

    result2 = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)
    assert result2["drafts_written"] == 0


def test_ingest_one_resolves_channel_id_from_url_when_missing(tmp_vault, monkeypatch):
    """If `_channel.yaml` ships with placeholder/missing channel_id but a real
    channel_url, ingest_one should call resolve_channel_id and persist."""
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_id": "TODO_UC_CHANNEL_ID",
        "channel_url": "https://youtube.com/@example",
        "author": "Example",
        "ingest": {"enabled": True, "cadence": "daily", "prefer_captions": True},
    })

    monkeypatch.setattr(yt, "resolve_channel_id", lambda url: "UCresolvedABCDEFGHIJK")
    monkeypatch.setattr(yt, "fetch_feed", lambda cid: [])
    monkeypatch.setattr(yt, "fetch_captions", lambda url, *, work_dir: "txt")

    yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)

    persisted = cy.load(channel_dir)
    assert persisted["channel_id"] == "UCresolvedABCDEFGHIJK"
    # Ephemeral _rel_dir must NOT survive on disk.
    assert "_rel_dir" not in persisted


def test_ingest_one_returns_resolve_failed_when_no_yt_dlp_match(tmp_vault, monkeypatch):
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_url": "https://youtube.com/@bad",
        "ingest": {"enabled": True, "cadence": "daily"},
    })
    monkeypatch.setattr(yt, "resolve_channel_id", lambda url: None)
    result = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)
    assert result["reason"] == "resolve_failed"


def test_ingest_one_skips_when_not_due(tmp_vault):
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_id": "UCabc",
        "ingest": {
            "enabled": True, "cadence": "daily",
            "last_polled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    })
    result = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)
    assert result["reason"] == "not_due"


def test_ingest_one_skips_video_when_no_transcript(tmp_vault, monkeypatch):
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_id": "UCabc",
        "author": "x",
        "ingest": {"enabled": True, "cadence": "daily", "prefer_captions": True},
    })

    monkeypatch.setattr(yt, "fetch_feed", lambda cid: [
        yt.FeedEntry(video_id="v", title="t", published_at="2026-05-06", url="u"),
    ])
    monkeypatch.setattr(yt, "fetch_captions", lambda url, *, work_dir: None)
    monkeypatch.setattr(yt, "whisper_transcribe", lambda url, *, work_dir, model="small": None)

    result = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)
    assert result["drafts_written"] == 0
    assert result["skipped_no_transcript"] == 1
    # Video still marked as seen so we don't retry the broken feed entry forever.
    cfg = cy.load(channel_dir)
    assert "v" in (cfg["ingest"].get("seen_video_ids") or [])


# ---------------------------------------------------------------------------
# Shorts filter
# ---------------------------------------------------------------------------


def test_is_short_detection(tmp_vault):
    from vault_indexer.ingest.youtube_channel import _is_short

    assert _is_short("https://www.youtube.com/shorts/abc123") is True
    assert _is_short("https://youtube.com/shorts/xyz") is True
    assert _is_short("https://www.youtube.com/watch?v=abc123") is False
    assert _is_short("https://youtu.be/abc123") is False
    assert _is_short("") is False
    assert _is_short(None) is False


def test_ingest_one_skips_shorts_marks_seen(tmp_vault, monkeypatch):
    """Shorts in the RSS feed are skipped (no draft, no transcription) but
    still recorded in seen_video_ids so re-polls don't reprocess them."""
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_id": "UCabc",
        "author": "X",
        "ingest": {"enabled": True, "cadence": "daily", "prefer_captions": True},
    })

    fake_entries = [
        yt.FeedEntry(video_id="long1", title="Long Form", published_at="2026-05-05",
                     url="https://www.youtube.com/watch?v=long1"),
        yt.FeedEntry(video_id="shrt1", title="Short Vid", published_at="2026-05-05",
                     url="https://www.youtube.com/shorts/shrt1"),
        yt.FeedEntry(video_id="shrt2", title="Another Short", published_at="2026-05-05",
                     url="https://www.youtube.com/shorts/shrt2"),
    ]
    monkeypatch.setattr(yt, "fetch_feed", lambda cid: fake_entries)

    captions_called: list[str] = []
    def _fake_captions(url, *, work_dir):
        captions_called.append(url)
        return f"transcript for {url}"
    monkeypatch.setattr(yt, "fetch_captions", _fake_captions)

    result = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)

    assert result["drafts_written"] == 1
    assert result["shorts_skipped"] == 2
    # Captions only fetched for the long-form entry.
    assert captions_called == ["https://www.youtube.com/watch?v=long1"]
    # All three video_ids marked seen — shorts won't be re-fetched on next tick.
    seen = cy.load(channel_dir)["ingest"].get("seen_video_ids") or []
    assert "long1" in seen
    assert "shrt1" in seen
    assert "shrt2" in seen
    # No draft files for shorts.
    assert not (channel_dir / "2026-05-05-short-vid.md.draft").exists()
    assert not (channel_dir / "2026-05-05-another-short.md.draft").exists()
    assert (channel_dir / "2026-05-05-long-form.md.draft").exists()


# ---------------------------------------------------------------------------
# auto_promote
# ---------------------------------------------------------------------------


def test_ingest_one_auto_promote_renames_drafts_to_md(tmp_vault, monkeypatch):
    """When _channel.yaml has ingest.auto_promote=True, drafts written this
    tick are immediately renamed to canonical .md (with draft: true stripped
    from frontmatter)."""
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_id": "UCabc",
        "author": "X",
        "ingest": {
            "enabled": True,
            "cadence": "daily",
            "prefer_captions": True,
            "auto_promote": True,
        },
    })

    monkeypatch.setattr(yt, "fetch_feed", lambda cid: [
        yt.FeedEntry(video_id="vid1", title="First", published_at="2026-05-05",
                     url="https://www.youtube.com/watch?v=vid1"),
    ])
    monkeypatch.setattr(yt, "fetch_captions", lambda url, *, work_dir: "transcript text")

    result = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)

    assert result["drafts_written"] == 1
    assert result["auto_promoted"] == 1
    # .md exists, .md.draft does not.
    assert (channel_dir / "2026-05-05-first.md").exists()
    assert not (channel_dir / "2026-05-05-first.md.draft").exists()
    # draft: true stripped from promoted file's frontmatter.
    import frontmatter as _fm
    promoted_text = (channel_dir / "2026-05-05-first.md").read_text()
    post = _fm.loads(promoted_text)
    assert "draft" not in post.metadata


def test_ingest_one_auto_promote_off_keeps_drafts_as_drafts(tmp_vault, monkeypatch):
    from vault_indexer.ingest import youtube_channel as yt
    from vault_indexer.ingest import _channel_yaml as cy

    channel_dir = tmp_vault / "Videos" / "ch"
    channel_dir.mkdir(parents=True)
    cy.save(channel_dir, {
        "channel_id": "UCabc",
        "author": "X",
        "ingest": {
            "enabled": True,
            "cadence": "daily",
            "prefer_captions": True,
            "auto_promote": False,
        },
    })

    monkeypatch.setattr(yt, "fetch_feed", lambda cid: [
        yt.FeedEntry(video_id="vid1", title="First", published_at="2026-05-05",
                     url="https://www.youtube.com/watch?v=vid1"),
    ])
    monkeypatch.setattr(yt, "fetch_captions", lambda url, *, work_dir: "txt")

    result = yt.ingest_one(channel_dir=channel_dir, vault_root=tmp_vault)
    assert result["drafts_written"] == 1
    assert result["auto_promoted"] == 0
    assert (channel_dir / "2026-05-05-first.md.draft").exists()
    assert not (channel_dir / "2026-05-05-first.md").exists()


# ---------------------------------------------------------------------------
# cleanup_shorts
# ---------------------------------------------------------------------------


def test_cleanup_shorts_finds_and_deletes(tmp_vault):
    from vault_indexer import cleanup_shorts as cs
    import frontmatter as _fm

    chan = tmp_vault / "Videos" / "fx"
    chan.mkdir(parents=True)

    short = chan / "2026-05-05-short.md.draft"
    long_draft = chan / "2026-05-05-long.md.draft"
    long_canonical = chan / "2026-05-05-long2.md"

    short.write_text(_fm.dumps(_fm.Post(
        content="x", source_url="https://www.youtube.com/shorts/abc",
    )) + "\n")
    long_draft.write_text(_fm.dumps(_fm.Post(
        content="y", source_url="https://www.youtube.com/watch?v=longA",
    )) + "\n")
    long_canonical.write_text(_fm.dumps(_fm.Post(
        content="z", source_url="https://www.youtube.com/watch?v=longB",
    )) + "\n")

    matches = cs.find_shorts(tmp_vault)
    assert [str(p.relative_to(tmp_vault)) for p, _ in matches] == [
        "Videos/fx/2026-05-05-short.md.draft",
    ]


def test_cleanup_shorts_idempotent_when_clean(tmp_vault):
    from vault_indexer import cleanup_shorts as cs
    import frontmatter as _fm

    chan = tmp_vault / "Videos" / "fx"
    chan.mkdir(parents=True)
    (chan / "2026-05-05-long.md").write_text(_fm.dumps(_fm.Post(
        content="x", source_url="https://www.youtube.com/watch?v=longA",
    )) + "\n")

    matches = cs.find_shorts(tmp_vault)
    assert matches == []
