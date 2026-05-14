"""Tests for tools.vault_indexer.ingest.whisper_adapter — MLX/torch routing.

No real audio transcription in CI; all backends mocked at the module level.
"""
from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.vault_indexer.ingest import whisper_adapter as wa


# ---------------------------------------------------------------------------
# _mlx_available platform gate
# ---------------------------------------------------------------------------


def test_mlx_available_force_torch_env_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_TORCH_WHISPER", "1")
    assert wa._mlx_available() is False


def test_mlx_available_non_apple_silicon_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORCE_TORCH_WHISPER", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert wa._mlx_available() is False


def test_mlx_available_intel_mac_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORCE_TORCH_WHISPER", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    assert wa._mlx_available() is False


def test_mlx_available_apple_silicon_with_pkg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORCE_TORCH_WHISPER", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    # mlx_whisper IS installed in this venv on M3, so should return True.
    assert wa._mlx_available() is True


# ---------------------------------------------------------------------------
# transcribe routing
# ---------------------------------------------------------------------------


def test_transcribe_missing_file_returns_empty() -> None:
    assert wa.transcribe(Path("/nonexistent/audio.mp3")) == ""


def test_transcribe_with_segments_missing_file_returns_empty_dict() -> None:
    result = wa.transcribe_with_segments(Path("/nonexistent/audio.mp3"))
    assert result == {"text": "", "segments": [], "language": ""}


def test_transcribe_routes_to_mlx_when_available(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    audio.touch()
    expected = {"text": "hello world", "segments": [], "language": "en"}
    with patch.object(wa, "_mlx_available", return_value=True), patch.object(
        wa, "_transcribe_mlx", return_value=expected
    ) as mlx_mock, patch.object(wa, "_transcribe_torch") as torch_mock:
        text = wa.transcribe(audio)
    assert text == "hello world"
    mlx_mock.assert_called_once()
    torch_mock.assert_not_called()


def test_transcribe_routes_to_torch_when_mlx_unavailable(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    audio.touch()
    expected = {"text": "torch path", "segments": [], "language": "en"}
    with patch.object(wa, "_mlx_available", return_value=False), patch.object(
        wa, "_transcribe_torch", return_value=expected
    ) as torch_mock, patch.object(wa, "_transcribe_mlx") as mlx_mock:
        text = wa.transcribe(audio)
    assert text == "torch path"
    torch_mock.assert_called_once()
    mlx_mock.assert_not_called()


def test_transcribe_failure_returns_empty(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    audio.touch()
    with patch.object(wa, "_mlx_available", return_value=True), patch.object(
        wa, "_transcribe_mlx", side_effect=RuntimeError("boom")
    ):
        text = wa.transcribe(audio)
    assert text == ""


def test_transcribe_with_segments_returns_full_shape(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    audio.touch()
    expected = {
        "text": "hello",
        "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
        "language": "en",
    }
    with patch.object(wa, "_mlx_available", return_value=True), patch.object(
        wa, "_transcribe_mlx", return_value=expected
    ):
        result = wa.transcribe_with_segments(audio)
    assert result == expected


def test_transcribe_strips_text_whitespace(tmp_path: Path) -> None:
    audio = tmp_path / "audio.mp3"
    audio.touch()
    with patch.object(wa, "_mlx_available", return_value=True), patch.object(
        wa, "_transcribe_mlx", return_value={"text": "  hello  ", "segments": [], "language": ""}
    ):
        assert wa.transcribe(audio) == "hello"


def test_backend_label_reflects_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_TORCH_WHISPER", "1")
    assert wa.backend_label() == "torch"
    monkeypatch.delenv("FORCE_TORCH_WHISPER")
    # arm64 darwin with mlx_whisper installed → "mlx"
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        assert wa.backend_label() == "mlx"
