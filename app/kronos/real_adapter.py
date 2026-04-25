"""Real Kronos adapter — loads vendored model + weights from Hugging Face.

Heavy dependency (torch, huggingface_hub) is imported LAZILY inside
`_ensure_loaded`. That way the main app (and test suite) stays thin unless
`KRONOS_ENABLED=true` flips to this adapter.

Model weights are cached per-process. First `predict()` for a given
`model_id` downloads from HF Hub into the local HF cache (point at a
Railway volume mount via the HF_HOME env var for persistence).

Inference flow:
1. Pull `context_length` (or fewer) most-recent bars from our OHLCV cache.
2. Build the DataFrame Kronos wants: columns [open, high, low, close,
   volume, amount] (volume/amount optional — Kronos fills zeros).
3. Build `x_timestamp` from our tz-aware UTC datetimes.
4. Synthesize `y_timestamp` by extrapolating the historical cadence
   `horizon_bars` steps forward.
5. Call `KronosPredictor.predict(...)` with conservative sampling defaults.
6. Return `PredictionResult` with a list-of-dicts forecast.
"""
from __future__ import annotations

import datetime
import logging
import threading
from typing import Any, Iterable

from app.kronos.adapter import ConstraintSpecMissingError, PredictionResult
from app.kronos.registry import ModelSpec, get_model
from app.kronos.schemas import Eligible
from app.market_data.intervals import minutes as interval_minutes

logger = logging.getLogger(__name__)

# Module-level caches. Initialised lazily so importing this module never
# triggers a torch/huggingface import.
_load_lock = threading.Lock()
_predictor_cache: dict[str, Any] = {}
_tokenizer_cache: dict[str, Any] = {}


def _import_runtime():
    """Lazy import of heavy deps. Raises a clear error if not installed."""
    try:
        import pandas as pd  # noqa: F401
        import torch  # noqa: F401

        from app.kronos._vendor.kronos_model import (
            Kronos,
            KronosPredictor,
            KronosTokenizer,
        )
    except ImportError as e:  # pragma: no cover - exercised only when extras missing
        raise ConstraintSpecMissingError(
            f"Kronos runtime import failed: {type(e).__name__}: {e}. "
            "Ensure requirements.txt installed (torch/einops/safetensors/huggingface_hub) "
            "and app/kronos/_vendor/kronos_model is present."
        ) from e
    return Kronos, KronosTokenizer, KronosPredictor


def _ensure_loaded(spec: ModelSpec):
    """Build (or return cached) KronosPredictor for `spec`."""
    with _load_lock:
        if spec.id in _predictor_cache:
            return _predictor_cache[spec.id]

        if not spec.hf_model or not spec.hf_tokenizer:
            raise ConstraintSpecMissingError(
                f"model '{spec.id}' missing hf_model / hf_tokenizer in registry"
            )

        Kronos, KronosTokenizer, KronosPredictor = _import_runtime()

        # Cache tokenizers across models that share one (base + small do).
        tok = _tokenizer_cache.get(spec.hf_tokenizer)
        if tok is None:
            logger.info("loading kronos tokenizer %s", spec.hf_tokenizer)
            tok = KronosTokenizer.from_pretrained(spec.hf_tokenizer)
            _tokenizer_cache[spec.hf_tokenizer] = tok

        logger.info("loading kronos model %s", spec.hf_model)
        model = Kronos.from_pretrained(spec.hf_model)
        predictor = KronosPredictor(model, tok, max_context=spec.context_length)
        _predictor_cache[spec.id] = predictor
        return predictor


def _to_dataframe(bars: Iterable[Any]):
    """Our OHLCV cache rows → pandas DataFrame in Kronos's expected shape."""
    import pandas as pd

    rows = []
    for b in bars:
        rows.append(
            {
                "timestamps": b.ts,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume if b.volume is not None else 0.0,
                "amount": b.amount if b.amount is not None else 0.0,
            }
        )
    if not rows:
        raise ValueError("no bars supplied to Kronos adapter")
    df = pd.DataFrame(rows)
    df["timestamps"] = pd.to_datetime(df["timestamps"], utc=True)
    df = df.sort_values("timestamps").reset_index(drop=True)
    return df


def _future_timestamps(df, interval: str, horizon: int):
    """Extend the trailing timestamp by `horizon` steps of `interval`."""
    import pandas as pd

    delta = pd.Timedelta(minutes=interval_minutes(interval))
    last = df["timestamps"].iloc[-1]
    return pd.Series([last + delta * (i + 1) for i in range(horizon)])


class RealKronosAdapter:
    """Production adapter. Defers all heavy imports until first `predict`."""

    def predict(self, eligible: Eligible, ohlcv: Any) -> PredictionResult:
        if not isinstance(eligible, Eligible):
            raise TypeError("RealKronosAdapter.predict requires an Eligible instance")

        spec = get_model(eligible.model_id)
        if spec is None:  # pragma: no cover - validator rejects before here
            raise ConstraintSpecMissingError(f"unknown model '{eligible.model_id}'")

        predictor = _ensure_loaded(spec)
        df = _to_dataframe(ohlcv)

        # ohlcv is assumed to be the window caller chose (e.g., last
        # context_length bars). We also need the corresponding interval.
        interval = None
        for row in ohlcv:
            interval = getattr(row, "interval", None)
            if interval:
                break
        if interval is None:
            raise ConstraintSpecMissingError(
                "ohlcv rows missing `interval` attribute required for horizon timestamps"
            )

        y_timestamp = _future_timestamps(df, interval, eligible.horizon_bars)
        x_df = df[["open", "high", "low", "close", "volume", "amount"]]

        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=df["timestamps"],
            y_timestamp=y_timestamp,
            pred_len=eligible.horizon_bars,
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )

        forecast = []
        for ts, row in zip(y_timestamp, pred_df.to_dict(orient="records")):
            forecast.append(
                {
                    "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "open": float(row.get("open", 0.0)),
                    "high": float(row.get("high", 0.0)),
                    "low": float(row.get("low", 0.0)),
                    "close": float(row.get("close", 0.0)),
                    "volume": float(row.get("volume", 0.0)),
                    "amount": float(row.get("amount", 0.0)),
                }
            )

        return PredictionResult(
            model_id=eligible.model_id,
            horizon_bars=eligible.horizon_bars,
            forecast=forecast,
            meta={
                "unverified": eligible.unverified,
                "context_length": eligible.context_length,
                "bars_used": len(df),
                "stub": False,
            },
        )


def activate() -> None:
    """Swap the module's adapter to the real one. Call from startup when
    `KRONOS_ENABLED=true`. Does not pre-load weights — first predict pays
    the download + load cost."""
    from app.kronos import adapter as _adapter

    _adapter.set_adapter(RealKronosAdapter())
    logger.info("kronos real adapter activated")
