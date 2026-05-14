"""Vision-Language Model adapter — MLX Qwen2-VL-2B for L3 chart-type captions.

Wraps ``mlx-vlm`` to produce a one-line caption per frame describing chart
type (candle / line / bar / area), tickers visible, and periodic windows.
Companion to ``video_vision.ocr_frame`` — the two are independent signals
that combine into a richer Visual Notes table when the operator enables
``vision.semantic_captions: true`` per ``_channel.yaml``.

Apple Silicon only (MLX is M1+ exclusive). On other platforms the
``available()`` check returns False and ``caption_frame()`` returns "".
Existing L2 (OCR) path is unaffected.

Model singleton: loaded lazily on the first call, cached at module level
for the lifetime of the process. Subsequent frames reuse the same model
instance — important since model load is ~10-15s while inference is
~1-2s on M3 (Qwen2-VL-2B-Instruct-4bit).

Failure contract: never raises. Returns "" on any error (import failure,
model load failure, generation error). Caller decides how to render the
empty case.

Note on thread-based timeouts: MLX maintains a thread-local GPU stream.
Generation in a worker thread (e.g. ThreadPoolExecutor) hits "There is
no Stream(gpu, 1) in current thread" on second-and-later calls. We run
inference in the caller's thread instead; the orchestrator's
``frame_budget`` cap bounds total per-video cost.
"""
from __future__ import annotations

import logging
import os
import platform
from pathlib import Path
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Model repo on HuggingFace. Pinned here so a community-repo rename
# doesn't silently break the channel poller.
#
# Picked Qwen2-VL-2B-Instruct (4-bit) for the right balance of:
#  - small (~1GB disk, 4-bit quantised)
#  - chart-reading quality on financial visuals
#  - actively maintained by mlx-community
#  - instruction-tuned (responds to "describe in one sentence" prompts well)
#
# Moondream2 isn't supported by mlx-vlm 0.5.x; only moondream3 has a class
# in mlx_vlm.models, and the MLX-ported weights aren't on HuggingFace yet
# as of 2026-05. Qwen2-VL is the closest equivalent.
DEFAULT_MODEL_REPO = "mlx-community/Qwen2-VL-2B-Instruct-4bit"

# Per-frame inference timeout. If MLX hangs on a malformed frame the
# whole channel poll shouldn't stall.
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 5.0

# Caption prompt. Concise + bounded so the LLM doesn't produce a
# multi-paragraph answer for a chart frame. Phrased so a non-chart
# frame (talking head, blank slide) yields a short trivial caption
# that the OCR-quality filter analog would skip later if desired.
DEFAULT_PROMPT = (
    "Describe this video frame in one short sentence. "
    "If it shows a financial chart, identify the chart type "
    "(candlestick, line, bar, area) and any visible timeframe "
    "(1D, 4H, weekly, etc). Otherwise describe what is shown."
)

DEFAULT_MAX_TOKENS = 60


# Module-level cache. (model, processor, config) tuple — None until
# the first successful load.
_MODEL_CACHE: Optional[tuple[Any, Any, Any]] = None
_LOAD_LOCK = Lock()
_LOAD_FAILED = False  # poison flag so we don't retry expensive loads


def available() -> bool:
    """Apple Silicon + mlx-vlm installed + not forced off via env."""
    if os.environ.get("DISABLE_MLX_VLM") == "1":
        return False
    if platform.system() != "Darwin":
        return False
    if platform.machine() != "arm64":
        return False
    try:
        import mlx_vlm  # noqa: F401
        return True
    except ImportError:
        return False


def _load_model(repo: str = DEFAULT_MODEL_REPO) -> Optional[tuple[Any, Any, Any]]:
    """Lazy singleton load. Returns (model, processor, config) or None."""
    global _MODEL_CACHE, _LOAD_FAILED
    if _LOAD_FAILED:
        return None
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    with _LOAD_LOCK:
        if _MODEL_CACHE is not None:
            return _MODEL_CACHE
        try:
            from mlx_vlm import load
            from mlx_vlm.utils import load_config

            logger.info("vlm_adapter: loading %s (first call, ~3-5s)", repo)
            model, processor = load(repo)
            config = load_config(repo)
            _MODEL_CACHE = (model, processor, config)
            logger.info("vlm_adapter: load complete")
            return _MODEL_CACHE
        except Exception as e:  # noqa: BLE001
            logger.warning("vlm_adapter: model load failed (%s); disabling L3", e)
            _LOAD_FAILED = True
            return None


def _generate_once(
    image_path: Path,
    *,
    prompt: str,
    max_tokens: int,
) -> str:
    """Single inference call. Returns caption string."""
    loaded = _load_model()
    if loaded is None:
        return ""
    model, processor, config = loaded

    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    formatted = apply_chat_template(processor, config, prompt, num_images=1)
    result = generate(
        model,
        processor,
        formatted,
        [str(image_path)],
        max_tokens=max_tokens,
        verbose=False,
    )
    # mlx-vlm's generate returns a GenerationResult dataclass in 0.5.x; older
    # versions return a string. Normalise both.
    if hasattr(result, "text"):
        text = result.text
    else:
        text = str(result)
    return _normalise(text)


def _normalise(text: str) -> str:
    """One-line caption, no leading punctuation, no trailing newlines."""
    if not text:
        return ""
    stripped = " ".join(text.split())  # collapse whitespace + newlines
    # Strip leading "The image shows" / "This image depicts" boilerplate
    # so the caption fits a table cell tightly. Cheap; safe to skip on
    # variants we don't match.
    for boilerplate in (
        "The image shows ", "This image shows ",
        "The image depicts ", "This image depicts ",
        "The frame shows ", "This frame shows ",
        "The video frame shows ", "This video frame shows ",
        "The video frame depicts ", "This video frame depicts ",
        "A frame showing ", "An image of ", "A video frame showing ",
    ):
        if stripped.lower().startswith(boilerplate.lower()):
            stripped = stripped[len(boilerplate):]
            stripped = stripped[:1].upper() + stripped[1:] if stripped else stripped
            break
    return stripped


def caption_frame(
    image_path: Path,
    *,
    prompt: str = DEFAULT_PROMPT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_seconds: float = DEFAULT_INFERENCE_TIMEOUT_SECONDS,
) -> str:
    """One-line caption for a single video frame. Never raises.

    Returns "" on:
      - MLX not available (non-Apple-Silicon or mlx-vlm not installed)
      - Model load failure (poisoned for the rest of the process)
      - Any exception during generation

    ``timeout_seconds`` is currently a no-op (MLX threading limitation,
    see module doc). Frame budget at the caller bounds total cost.
    """
    del timeout_seconds  # kept for API forwards-compat
    if not available():
        return ""
    if not Path(image_path).exists():
        return ""

    # Lazy singleton load. Returns None if poisoned (load failed earlier).
    if _load_model() is None:
        return ""

    try:
        return _generate_once(image_path, prompt=prompt, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001
        logger.warning("vlm_adapter: generation failed: %s", e)
        return ""


def reset_model_cache() -> None:
    """Test hook + manual reload. Drops the cached model so the next
    ``caption_frame`` call re-loads from HuggingFace.
    """
    global _MODEL_CACHE, _LOAD_FAILED
    _MODEL_CACHE = None
    _LOAD_FAILED = False
