"""Whisper transcription adapter — Apple Silicon MLX with torch fallback.

Existing call sites (`ingest_video.py`, `youtube_channel.py:whisper_transcribe`)
import from here instead of from openai-whisper directly. The adapter
routes:
  - Apple Silicon + mlx-whisper installed → MLX path (3-5× faster on M3)
  - Otherwise → openai-whisper torch path (preserved verbatim)

Override env:
  FORCE_TORCH_WHISPER=1  → force torch path (debugging + CI safety)

Mocking strategy for tests: patch ``_mlx_available`` or the module-level
``_transcribe_mlx`` / ``_transcribe_torch`` functions to avoid real
audio inference in CI.
"""
from __future__ import annotations

import logging
import os
import platform
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# MLX-Whisper expects HuggingFace repo IDs of the form
# "mlx-community/whisper-<size>-mlx". Map the openai-whisper short names
# to the MLX repos. Pinning here keeps the operator one-line away from
# rolling back if a community repo goes away.
_MLX_REPO_BY_MODEL: dict[str, str] = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}


def _mlx_available() -> bool:
    """Apple Silicon + mlx-whisper installed + not forced off via env."""
    if os.environ.get("FORCE_TORCH_WHISPER") == "1":
        return False
    if platform.system() != "Darwin":
        return False
    if platform.machine() != "arm64":
        return False
    try:
        import mlx_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _transcribe_mlx(audio_path: Path, model: str) -> dict[str, Any]:
    """MLX path. Returns the same dict shape as openai-whisper's transcribe()."""
    import mlx_whisper  # heavy lazy import

    repo = _MLX_REPO_BY_MODEL.get(model, _MLX_REPO_BY_MODEL["small"])
    result = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=repo)
    # mlx_whisper returns {"text": str, "segments": list[dict], "language": str}
    # — same shape as openai-whisper. Normalise just in case for defensive parity.
    return {
        "text": result.get("text", "") or "",
        "segments": result.get("segments", []) or [],
        "language": result.get("language", ""),
    }


def _transcribe_torch(audio_path: Path, model: str) -> dict[str, Any]:
    """openai-whisper torch path — preserved verbatim from prior code."""
    import whisper  # heavy lazy import

    m = whisper.load_model(model)
    result = m.transcribe(str(audio_path))
    return {
        "text": (result.get("text") or "").strip(),
        "segments": result.get("segments", []) or [],
        "language": result.get("language", ""),
    }


def transcribe(audio_path: Path, *, model: str = "small") -> str:
    """Transcribe an audio file. Returns the text body (matches existing API).

    Never raises — failure returns "". Existing callers can keep
    treating "" as "no transcript available; skip draft."
    """
    if not Path(audio_path).exists():
        return ""
    try:
        if _mlx_available():
            data = _transcribe_mlx(Path(audio_path), model)
        else:
            data = _transcribe_torch(Path(audio_path), model)
    except Exception as e:  # noqa: BLE001
        logger.warning("whisper transcription failed: %s", e)
        return ""
    return (data.get("text") or "").strip()


def transcribe_with_segments(audio_path: Path, *, model: str = "small") -> dict[str, Any]:
    """Full transcribe result including segments + language.

    Used by future L3 audio-aligned frame extraction. Same backend
    routing as ``transcribe()``. Returns ``{"text": "", "segments": [],
    "language": ""}`` on any failure.
    """
    if not Path(audio_path).exists():
        return {"text": "", "segments": [], "language": ""}
    try:
        if _mlx_available():
            return _transcribe_mlx(Path(audio_path), model)
        return _transcribe_torch(Path(audio_path), model)
    except Exception as e:  # noqa: BLE001
        logger.warning("whisper transcription failed: %s", e)
        return {"text": "", "segments": [], "language": ""}


def backend_label() -> str:
    """Diagnostic helper — returns 'mlx' or 'torch'."""
    return "mlx" if _mlx_available() else "torch"
