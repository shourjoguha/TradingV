"""Tests for tools.vault_indexer.ingest.vlm_adapter — Moondream2 L3 caption.

No real model load in CI. ``_generate_once`` patched; timeout path tested.
"""
from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.vault_indexer.ingest import vlm_adapter as va


# ---------------------------------------------------------------------------
# Availability gate
# ---------------------------------------------------------------------------


def test_available_disable_env_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISABLE_MLX_VLM", "1")
    assert va.available() is False


def test_available_non_apple_silicon_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISABLE_MLX_VLM", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert va.available() is False


def test_available_intel_mac_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISABLE_MLX_VLM", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    assert va.available() is False


def test_available_apple_silicon_with_pkg() -> None:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        assert va.available() is True


# ---------------------------------------------------------------------------
# caption_frame contract: never raises, returns "" on all failure modes
# ---------------------------------------------------------------------------


def test_caption_frame_unavailable_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISABLE_MLX_VLM", "1")
    assert va.caption_frame(Path("/anything.png")) == ""


def test_caption_frame_missing_file_returns_empty(tmp_path: Path) -> None:
    assert va.caption_frame(tmp_path / "no-such.png") == ""


_FAKE_LOADED = ("fake_model", "fake_processor", "fake_config")


def test_caption_frame_returns_generated_text(tmp_path: Path) -> None:
    img = tmp_path / "frame.png"
    img.touch()
    with patch.object(va, "_load_model", return_value=_FAKE_LOADED), patch.object(
        va, "_generate_once", return_value="Candlestick chart of BTC"
    ):
        result = va.caption_frame(img)
    assert result == "Candlestick chart of BTC"


def test_caption_frame_generation_failure_returns_empty(tmp_path: Path) -> None:
    img = tmp_path / "frame.png"
    img.touch()
    with patch.object(va, "_load_model", return_value=_FAKE_LOADED), patch.object(
        va, "_generate_once", side_effect=RuntimeError("inference failed")
    ):
        result = va.caption_frame(img)
    assert result == ""


def test_caption_frame_load_failure_returns_empty(tmp_path: Path) -> None:
    """Poisoned model load (returns None) → caption_frame short-circuits."""
    img = tmp_path / "frame.png"
    img.touch()
    with patch.object(va, "_load_model", return_value=None):
        result = va.caption_frame(img)
    assert result == ""


def test_caption_frame_timeout_param_accepted_but_no_op(tmp_path: Path) -> None:
    """timeout_seconds kept for API forwards-compat but currently a no-op
    (MLX thread-local GPU stream limitation). Confirm passing it doesn't
    crash; actual generation completes via the patched _generate_once."""
    img = tmp_path / "frame.png"
    img.touch()
    with patch.object(va, "_load_model", return_value=_FAKE_LOADED), patch.object(
        va, "_generate_once", return_value="line chart"
    ):
        result = va.caption_frame(img, timeout_seconds=0.1)
    assert result == "line chart"


# ---------------------------------------------------------------------------
# Normalisation — caption boilerplate strip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", ""),
        ("Candlestick chart", "Candlestick chart"),
        ("The image shows a candlestick chart", "A candlestick chart"),
        ("This image shows a line graph", "A line graph"),
        ("The image depicts a bar chart", "A bar chart"),
        ("A frame showing the S&P 500", "The S&P 500"),
        # Whitespace collapse
        ("foo\n\nbar  baz\n", "foo bar baz"),
    ],
)
def test_normalise_strips_boilerplate(raw: str, expected: str) -> None:
    assert va._normalise(raw) == expected


# ---------------------------------------------------------------------------
# Cache reset hook
# ---------------------------------------------------------------------------


def test_reset_model_cache_clears_singleton_and_poison() -> None:
    va._MODEL_CACHE = ("fake_model", "fake_processor", "fake_config")
    va._LOAD_FAILED = True
    va.reset_model_cache()
    assert va._MODEL_CACHE is None
    assert va._LOAD_FAILED is False
