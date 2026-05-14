"""Tests for tools.vault_indexer.ingest.video_vision (L2 — Scene + OCR).

No real ffmpeg, yt-dlp, or Tesseract invocations in CI — every external
boundary is patched. Tests cover:
  - ffmpeg stderr parsing
  - 3-stage filter (threshold via scene_score, time-gap, budget)
  - OCR noise filter
  - Markdown rendering (empty + populated + truncated note + pipe escape)
  - VisionConfig YAML parsing
  - process_video disabled-cfg short-circuit
  - process_video graceful degradation when video download fails
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.vault_indexer.ingest import video_vision as v
from tools.vault_indexer.ingest.video_vision import (
    SceneCandidate,
    VisionConfig,
    VisionResult,
)


# ---------------------------------------------------------------------------
# ffmpeg stderr parser
# ---------------------------------------------------------------------------


def test_parse_ffmpeg_scene_stderr_pairs_ts_and_score() -> None:
    sample = (
        "[Parsed_metadata_3 @ 0x6000] frame:42 pts:12345 pts_time:1.234\n"
        "[Parsed_metadata_3 @ 0x6000] lavfi.scene_score=0.156421\n"
        "[Parsed_metadata_3 @ 0x6000] frame:120 pts:56789 pts_time:5.678\n"
        "[Parsed_metadata_3 @ 0x6000] lavfi.scene_score=0.823456\n"
        "some unrelated log line\n"
        "[Parsed_metadata_3 @ 0x6000] frame:200 pts:99999 pts_time:10.5\n"
        "[Parsed_metadata_3 @ 0x6000] lavfi.scene_score=0.314159\n"
    )
    pairs = v._parse_ffmpeg_scene_stderr(sample)
    assert pairs == [(1.234, 0.156421), (5.678, 0.823456), (10.5, 0.314159)]


def test_parse_ffmpeg_scene_stderr_empty_input() -> None:
    assert v._parse_ffmpeg_scene_stderr("") == []


def test_parse_ffmpeg_scene_stderr_handles_orphan_pts() -> None:
    """A pts_time line without a following scene_score is dropped, not crashed."""
    sample = (
        "[Parsed_metadata @ 0x] pts_time:1.0\n"
        "no score follows\n"
        "[Parsed_metadata @ 0x] pts_time:2.0\n"
        "[Parsed_metadata @ 0x] lavfi.scene_score=0.5\n"
    )
    pairs = v._parse_ffmpeg_scene_stderr(sample)
    assert pairs == [(2.0, 0.5)]


# ---------------------------------------------------------------------------
# Stage 2: time-gap dedupe
# ---------------------------------------------------------------------------


def _cand(ts: float, score: float = 0.5) -> SceneCandidate:
    return SceneCandidate(timestamp_seconds=ts, scene_score=score, frame_path=Path(f"/tmp/f{ts}.png"))


def test_time_gap_dedupe_collapses_rapid_succession() -> None:
    cands = [_cand(0.0), _cand(2.0), _cand(5.0), _cand(15.0), _cand(18.0)]
    out = v.apply_time_gap_dedupe(cands, min_gap_seconds=10)
    assert [c.timestamp_seconds for c in out] == [0.0, 15.0]


def test_time_gap_dedupe_zero_gap_passthrough() -> None:
    cands = [_cand(0.0), _cand(1.0), _cand(2.0)]
    out = v.apply_time_gap_dedupe(cands, min_gap_seconds=0)
    assert len(out) == 3


def test_time_gap_dedupe_empty_input() -> None:
    assert v.apply_time_gap_dedupe([], min_gap_seconds=10) == []


# ---------------------------------------------------------------------------
# Stage 4: budget cap
# ---------------------------------------------------------------------------


def test_budget_cap_under_budget_passes_through() -> None:
    cands = [_cand(i * 5.0, score=0.5) for i in range(3)]
    capped, truncated = v.apply_budget_cap(cands, budget=10)
    assert capped == cands
    assert truncated is False


def test_budget_cap_over_budget_keeps_top_score_in_time_order() -> None:
    cands = [_cand(i * 5.0, score=0.1 * i) for i in range(10)]
    # Scores: 0.0, 0.1, 0.2, ..., 0.9. Top 3 = indices 7,8,9 (ts 35,40,45).
    capped, truncated = v.apply_budget_cap(cands, budget=3)
    assert truncated is True
    assert [c.timestamp_seconds for c in capped] == [35.0, 40.0, 45.0]
    # Verify time-ordered, not score-ordered output.
    assert capped[0].timestamp_seconds < capped[1].timestamp_seconds


# ---------------------------------------------------------------------------
# OCR noise filter (covers the cursor-wiggle + animation-frame skip)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", False),
        ("   ", False),
        ("a", False),         # < 3 alnum
        ("!@#", False),       # 0 alnum
        ("!@#$%^&*()_-+=", False),  # 0% alnum
        ("!@#$%^&*ab", False),  # 2/10 = 20% alnum ratio
        ("BTC 40000", True),
        ("40,000", True),
        ("S&P 500", True),
    ],
)
def test_ocr_text_quality_filter(text: str, expected: bool) -> None:
    assert v._ocr_text_passes_quality(text) is expected


def test_normalize_ocr_text_collapses_whitespace() -> None:
    assert v._normalize_ocr_text("foo\n\nbar  baz\n") == "foo bar baz"
    assert v._normalize_ocr_text("") == ""


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def test_render_visual_notes_empty_input_returns_empty() -> None:
    assert v.render_visual_notes_table([]) == ""


def test_render_visual_notes_all_empty_text_returns_empty() -> None:
    assert v.render_visual_notes_table([(0.0, ""), (5.0, "")]) == ""


def test_render_visual_notes_table_basic() -> None:
    md = v.render_visual_notes_table(
        [(42.0, "BTC 40000 daily"), (134.0, "DXY weekly"), (180.0, "")]
    )
    assert "## Visual notes" in md
    assert "0:42" in md
    assert "2:14" in md
    # Empty-text row dropped, so 3:00 should NOT appear.
    assert "3:00" not in md


def test_render_visual_notes_table_truncated_note() -> None:
    md = v.render_visual_notes_table([(0.0, "foo")], truncated=True)
    assert "frame count exceeded budget" in md


def test_render_visual_notes_table_pipe_escape() -> None:
    md = v.render_visual_notes_table([(0.0, "foo|bar|baz")])
    assert "foo\\|bar\\|baz" in md


def test_format_timestamp_handles_hours() -> None:
    assert v._format_timestamp(42) == "0:42"
    assert v._format_timestamp(134) == "2:14"
    assert v._format_timestamp(3661) == "1:01:01"
    assert v._format_timestamp(7200) == "2:00:00"


# ---------------------------------------------------------------------------
# VisionConfig
# ---------------------------------------------------------------------------


def test_vision_config_absent_is_disabled() -> None:
    c = VisionConfig.from_mapping(None)
    assert c.enabled is False


def test_vision_config_empty_dict_is_disabled() -> None:
    c = VisionConfig.from_mapping({})
    assert c.enabled is False


def test_vision_config_parses_full_yaml_block() -> None:
    raw = {
        "enabled": True,
        "frame_budget": 25,
        "scene_threshold": 0.15,
        "min_gap_seconds": 8,
        "ssim_threshold": 0.95,
        "ocr_lang": "eng+fra",
        "semantic_captions": False,
    }
    c = VisionConfig.from_mapping(raw)
    assert c.enabled is True
    assert c.frame_budget == 25
    assert c.scene_threshold == 0.15
    assert c.min_gap_seconds == 8
    assert c.ssim_threshold == 0.95
    assert c.ocr_lang == "eng+fra"


def test_vision_config_ssim_none_disables_stage_3() -> None:
    c = VisionConfig.from_mapping({"enabled": True, "ssim_threshold": None})
    assert c.ssim_threshold is None


def test_vision_config_multi_domain_reuse() -> None:
    """Same VisionConfig path works for any channel YAML — finance / fitness / nutrition."""
    # Simulate a fitness channel YAML
    raw = {"enabled": True, "frame_budget": 20, "ocr_lang": "eng"}
    c = VisionConfig.from_mapping(raw)
    assert c.enabled is True
    assert c.frame_budget == 20


# ---------------------------------------------------------------------------
# process_video orchestrator: short-circuits + graceful failures
# ---------------------------------------------------------------------------


def test_process_video_disabled_cfg_no_op() -> None:
    cfg = VisionConfig(enabled=False)
    result = v.process_video("https://x/v?v=abc", cfg=cfg)
    assert isinstance(result, VisionResult)
    assert result.markdown == ""
    assert result.frame_count == 0
    assert result.diagnostics.get("reason") == "vision_disabled"


def test_process_video_download_failure_returns_empty(tmp_path: Path) -> None:
    cfg = VisionConfig(enabled=True)
    with patch.object(v, "_download_video", return_value=None):
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    assert result.markdown == ""
    assert result.diagnostics.get("reason") == "download_failed"


def test_process_video_no_scene_frames_returns_empty(tmp_path: Path) -> None:
    cfg = VisionConfig(enabled=True)
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=([], False)
    ):
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    assert result.markdown == ""
    assert result.diagnostics.get("reason") == "no_scene_frames"


def test_process_video_full_path_renders_markdown(tmp_path: Path) -> None:
    """Happy path: download → frames → OCR → markdown."""
    cfg = VisionConfig(enabled=True, frame_budget=10)
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    fake_frames = [
        SceneCandidate(timestamp_seconds=42.0, scene_score=0.5, frame_path=tmp_path / "f1.png"),
        SceneCandidate(timestamp_seconds=134.0, scene_score=0.6, frame_path=tmp_path / "f2.png"),
    ]
    # Real OCR would inspect files; patch to deterministic returns.
    ocr_responses = iter(["BTC 40000", "DXY weekly"])
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=(fake_frames, False)
    ), patch.object(v, "ocr_frame", side_effect=lambda *a, **kw: next(ocr_responses)):
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    assert result.frame_count == 2
    assert "## Visual notes" in result.markdown
    assert "BTC 40000" in result.markdown
    assert "DXY weekly" in result.markdown
    assert "0:42" in result.markdown
    assert "2:14" in result.markdown
    # Without semantic_captions: 2-column table
    assert "| Time | On-screen text |" in result.markdown
    assert "| Time | Visual |" not in result.markdown
    assert result.diagnostics.get("captions_enabled") is False


# ---------------------------------------------------------------------------
# L3 — 3-column table + VLM wiring
# ---------------------------------------------------------------------------


def test_render_visual_notes_3col_with_captions() -> None:
    md = v.render_visual_notes_table(
        [(42.0, "BTC 40000"), (134.0, "DXY weekly")],
        captions=[(42.0, "candlestick chart"), (134.0, "line chart")],
    )
    assert "| Time | Visual | On-screen text |" in md
    assert "candlestick chart" in md
    assert "BTC 40000" in md


def test_render_visual_notes_3col_keeps_caption_only_rows() -> None:
    """A row with caption but blank OCR should still render (caption alone is signal)."""
    md = v.render_visual_notes_table(
        [(42.0, "")],
        captions=[(42.0, "candlestick chart")],
    )
    assert "candlestick chart" in md
    assert "| 0:42 |" in md


def test_render_visual_notes_3col_drops_double_empty() -> None:
    """Row with both OCR and caption empty must NOT render."""
    md = v.render_visual_notes_table(
        [(42.0, ""), (50.0, "BTC")],
        captions=[(42.0, ""), (50.0, "")],
    )
    # 0:42 row dropped (both empty); 0:50 kept (OCR present)
    assert "0:42" not in md
    assert "BTC" in md


def test_render_visual_notes_2col_byte_identical_when_captions_none() -> None:
    """Regression: callers passing captions=None must get the L2 2-col output."""
    md_a = v.render_visual_notes_table([(42.0, "BTC 40000")])
    md_b = v.render_visual_notes_table([(42.0, "BTC 40000")], captions=None)
    assert md_a == md_b
    assert "| Time | On-screen text |" in md_a
    assert "Visual |" not in md_a


def test_process_video_semantic_captions_disabled_no_vlm_call(tmp_path: Path) -> None:
    """L3 off → vlm_adapter never invoked. Regression coverage for L2 channels."""
    cfg = VisionConfig(enabled=True, frame_budget=10, semantic_captions=False)
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    fake_frames = [
        SceneCandidate(timestamp_seconds=42.0, scene_score=0.5, frame_path=tmp_path / "f1.png"),
    ]
    from tools.vault_indexer.ingest import vlm_adapter as _vlm
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=(fake_frames, False)
    ), patch.object(v, "ocr_frame", return_value="BTC"), patch.object(
        _vlm, "caption_frame"
    ) as vlm_mock:
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    vlm_mock.assert_not_called()
    assert "Visual |" not in result.markdown
    assert result.diagnostics.get("captions_enabled") is False


def test_process_video_semantic_captions_enabled_calls_vlm(tmp_path: Path) -> None:
    """L3 on → vlm_adapter.caption_frame invoked per frame; 3-col table output."""
    cfg = VisionConfig(enabled=True, frame_budget=10, semantic_captions=True)
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    fake_frames = [
        SceneCandidate(timestamp_seconds=42.0, scene_score=0.5, frame_path=tmp_path / "f1.png"),
        SceneCandidate(timestamp_seconds=134.0, scene_score=0.6, frame_path=tmp_path / "f2.png"),
    ]
    caps = iter(["Candlestick chart of BTC", "Line chart of DXY"])
    ocrs = iter(["BTC 40000", "DXY"])
    from tools.vault_indexer.ingest import vlm_adapter as _vlm
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=(fake_frames, False)
    ), patch.object(v, "ocr_frame", side_effect=lambda *a, **kw: next(ocrs)), patch.object(
        _vlm, "available", return_value=True
    ), patch.object(_vlm, "caption_frame", side_effect=lambda *a, **kw: next(caps)):
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    assert "| Time | Visual | On-screen text |" in result.markdown
    assert "Candlestick chart of BTC" in result.markdown
    assert "Line chart of DXY" in result.markdown
    assert "BTC 40000" in result.markdown
    assert result.diagnostics.get("captions_enabled") is True
    assert result.diagnostics.get("kept_caption_rows") == 2


def test_process_video_captions_enabled_but_vlm_unavailable_falls_back_to_l2(tmp_path: Path) -> None:
    """semantic_captions: true but mlx-vlm not available → silently degrade to L2."""
    cfg = VisionConfig(enabled=True, frame_budget=10, semantic_captions=True)
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    fake_frames = [
        SceneCandidate(timestamp_seconds=42.0, scene_score=0.5, frame_path=tmp_path / "f1.png"),
    ]
    from tools.vault_indexer.ingest import vlm_adapter as _vlm
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=(fake_frames, False)
    ), patch.object(v, "ocr_frame", return_value="BTC"), patch.object(
        _vlm, "available", return_value=False
    ), patch.object(_vlm, "caption_frame") as vlm_mock:
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    vlm_mock.assert_not_called()
    # Falls back to 2-col table
    assert "Visual |" not in result.markdown
    assert result.diagnostics.get("captions_enabled") is False


def test_vision_config_semantic_captions_default_false() -> None:
    cfg = VisionConfig.from_mapping({"enabled": True})
    assert cfg.semantic_captions is False


def test_vision_config_semantic_captions_yaml_flag() -> None:
    cfg = VisionConfig.from_mapping({"enabled": True, "semantic_captions": True})
    assert cfg.semantic_captions is True


# ---------------------------------------------------------------------------
# chart_extraction nested config + 2-stage extraction wiring
# ---------------------------------------------------------------------------


def test_vision_config_chart_extraction_defaults_off() -> None:
    cfg = VisionConfig.from_mapping({"enabled": True})
    assert cfg.chart_extraction.enabled is False
    assert cfg.chart_extraction.rollup_cap == 10


def test_vision_config_chart_extraction_nested_parse() -> None:
    cfg = VisionConfig.from_mapping({
        "enabled": True,
        "chart_extraction": {"enabled": True, "rollup_cap": 5},
    })
    assert cfg.chart_extraction.enabled is True
    assert cfg.chart_extraction.rollup_cap == 5


def test_vision_config_chart_extraction_handles_malformed() -> None:
    """Missing or non-dict chart_extraction → defaults to disabled."""
    cfg = VisionConfig.from_mapping({"enabled": True, "chart_extraction": None})
    assert cfg.chart_extraction.enabled is False
    cfg = VisionConfig.from_mapping({"enabled": True, "chart_extraction": "garbage"})
    assert cfg.chart_extraction.enabled is False


def test_process_video_chart_extraction_enabled_collects_structured(tmp_path: Path) -> None:
    from tools.vault_indexer.ingest.video_vision import ChartExtractionConfig

    cfg = VisionConfig(
        enabled=True,
        frame_budget=10,
        chart_extraction=ChartExtractionConfig(enabled=True, rollup_cap=10),
    )
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    fake_frames = [
        SceneCandidate(timestamp_seconds=42.0, scene_score=0.5, frame_path=tmp_path / "f1.png"),
    ]
    from tools.vault_indexer.ingest import vlm_adapter as _vlm
    from tools.vault_indexer.ingest import chart_extractor as _ce
    structured_response = {
        "chart_type": "candlestick",
        "timeframe": "4h",
        "tickers": ["BTC"],
        "topics": ["bubble parallel"],
        "caption": "Candlestick chart of BTC on 4H",
        "raw": "...",
        "parse_failed": False,
    }
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=(fake_frames, False)
    ), patch.object(v, "ocr_frame", return_value="BTC"), patch.object(
        _vlm, "available", return_value=True
    ), patch.object(
        _vlm, "caption_frame_structured", return_value=structured_response
    ), patch.object(_ce, "load_ticker_whitelist_sync", return_value={"BTC"}):
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    assert len(result.chart_references) == 1
    ref = result.chart_references[0]
    assert ref["chart_type"] == "candlestick"
    assert ref["timeframe"] == "4h"
    assert ref["tickers"] == ["BTC"]
    assert ref["topics"] == ["bubble parallel"]
    assert result.unknown_tickers == []
    assert result.diagnostics["chart_extraction_enabled"] is True


def test_process_video_chart_extraction_collects_unknown_tickers(tmp_path: Path) -> None:
    """Stage 1 emits PLTR (not in whitelist) → unknown_tickers captures it."""
    from tools.vault_indexer.ingest.video_vision import ChartExtractionConfig

    cfg = VisionConfig(
        enabled=True,
        frame_budget=10,
        chart_extraction=ChartExtractionConfig(enabled=True),
    )
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    fake_frames = [
        SceneCandidate(timestamp_seconds=10.0, scene_score=0.5, frame_path=tmp_path / "f1.png"),
    ]
    from tools.vault_indexer.ingest import vlm_adapter as _vlm
    from tools.vault_indexer.ingest import chart_extractor as _ce
    structured_response = {
        "chart_type": "candlestick",
        "timeframe": "1d",
        "tickers": ["PLTR"],
        "topics": [],
        "caption": "PLTR on 1D",
        "raw": "...",
        "parse_failed": False,
    }
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=(fake_frames, False)
    ), patch.object(v, "ocr_frame", return_value=""), patch.object(
        _vlm, "available", return_value=True
    ), patch.object(
        _vlm, "caption_frame_structured", return_value=structured_response
    ), patch.object(_ce, "load_ticker_whitelist_sync", return_value={"BTC", "META"}):
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    # PLTR not in whitelist → goes to unknown bucket.
    assert "PLTR" in result.unknown_tickers


def test_process_video_chart_extraction_yaml_fail_uses_heuristic(tmp_path: Path) -> None:
    """parse_failed=True path → chart_extractor fallback salvages from caption."""
    from tools.vault_indexer.ingest.video_vision import ChartExtractionConfig

    cfg = VisionConfig(
        enabled=True,
        frame_budget=10,
        chart_extraction=ChartExtractionConfig(enabled=True),
    )
    fake_video = tmp_path / "video.mp4"
    fake_video.touch()
    fake_frames = [
        SceneCandidate(timestamp_seconds=10.0, scene_score=0.5, frame_path=tmp_path / "f1.png"),
    ]
    from tools.vault_indexer.ingest import vlm_adapter as _vlm
    from tools.vault_indexer.ingest import chart_extractor as _ce
    # YAML parse failed but caption salvageable by regex.
    structured_response = {
        "chart_type": None,
        "timeframe": None,
        "tickers": [],
        "topics": [],
        "caption": "Candlestick chart of BTC on 4H",
        "raw": "garbled output",
        "parse_failed": True,
    }
    with patch.object(v, "_download_video", return_value=fake_video), patch.object(
        v, "extract_scene_frames", return_value=(fake_frames, False)
    ), patch.object(v, "ocr_frame", return_value=""), patch.object(
        _vlm, "available", return_value=True
    ), patch.object(
        _vlm, "caption_frame_structured", return_value=structured_response
    ), patch.object(_ce, "load_ticker_whitelist_sync", return_value={"BTC"}):
        result = v.process_video("https://x/v?v=abc", cfg=cfg, work_dir=tmp_path)
    # Heuristic salvaged the fields from the caption.
    assert len(result.chart_references) == 1
    ref = result.chart_references[0]
    assert ref["chart_type"] == "candlestick"
    assert ref["timeframe"] == "4h"
    assert ref["tickers"] == ["BTC"]
