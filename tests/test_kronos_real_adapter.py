"""Smoke test for the real Kronos adapter's plumbing.

Does NOT install torch/kronos_model — monkeypatches the lazy `_import_runtime`
hook with a fake `KronosPredictor` so we exercise registry lookup, DataFrame
construction, timestamp extrapolation, and `PredictionResult` shaping.
"""
from __future__ import annotations

import datetime
import sys
import types
from dataclasses import dataclass

import pytest

from app.kronos import real_adapter
from app.kronos.schemas import Eligible


@dataclass
class _FakeBar:
    ts: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None
    interval: str


class _FakePredictor:
    """Mimics KronosPredictor.predict — returns a df of the right shape."""

    def __init__(self, *_a, **_kw):
        pass

    def predict(self, df, x_timestamp, y_timestamp, pred_len, **_kw):
        import pandas as pd

        return pd.DataFrame(
            {
                "open": [1.0] * pred_len,
                "high": [1.0] * pred_len,
                "low": [1.0] * pred_len,
                "close": [1.0] * pred_len,
                "volume": [0.0] * pred_len,
                "amount": [0.0] * pred_len,
            }
        )


class _FakeTokenizer:
    @classmethod
    def from_pretrained(cls, _id):
        return cls()


class _FakeModel:
    @classmethod
    def from_pretrained(cls, _id):
        return cls()


@pytest.fixture(autouse=True)
def _clear_caches():
    real_adapter._predictor_cache.clear()
    real_adapter._tokenizer_cache.clear()
    yield
    real_adapter._predictor_cache.clear()
    real_adapter._tokenizer_cache.clear()


def _install_fake_runtime(monkeypatch):
    monkeypatch.setattr(
        real_adapter,
        "_import_runtime",
        lambda: (_FakeModel, _FakeTokenizer, lambda model, tok, max_context: _FakePredictor()),
    )


@pytest.mark.asyncio
async def test_real_adapter_shapes_prediction_result(monkeypatch):
    _install_fake_runtime(monkeypatch)

    base_ts = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    bars = [
        _FakeBar(
            ts=base_ts + datetime.timedelta(days=i),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
            amount=1.0,
            interval="1d",
        )
        for i in range(450)
    ]

    adapter = real_adapter.RealKronosAdapter()
    eligible = Eligible(
        model_id="kronos_base", horizon_bars=10, context_length=512, unverified=True
    )
    result = adapter.predict(eligible, bars)

    assert result.model_id == "kronos_base"
    assert result.horizon_bars == 10
    assert len(result.forecast) == 10
    # Horizon timestamps extrapolate by the interval cadence (1 day).
    first_future = datetime.datetime.fromisoformat(result.forecast[0]["ts"])
    expected = bars[-1].ts + datetime.timedelta(days=1)
    assert first_future == expected
    assert result.meta["stub"] is False
    assert result.meta["bars_used"] == 450


@pytest.mark.asyncio
async def test_real_adapter_rejects_non_eligible(monkeypatch):
    _install_fake_runtime(monkeypatch)
    adapter = real_adapter.RealKronosAdapter()
    with pytest.raises(TypeError):
        adapter.predict("not-eligible", [])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_real_adapter_unknown_model_raises(monkeypatch):
    _install_fake_runtime(monkeypatch)
    adapter = real_adapter.RealKronosAdapter()
    eligible = Eligible(
        model_id="kronos_vapor", horizon_bars=5, context_length=512, unverified=True
    )
    from app.kronos.adapter import ConstraintSpecMissingError

    with pytest.raises(ConstraintSpecMissingError):
        adapter.predict(eligible, [])


@pytest.mark.asyncio
async def test_real_adapter_rejects_rows_without_interval(monkeypatch):
    _install_fake_runtime(monkeypatch)
    # Bars missing the `interval` attribute.
    base_ts = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

    class _BarNoInterval:
        def __init__(self, ts):
            self.ts = ts
            self.open = self.high = self.low = self.close = 1.0
            self.volume = 1.0
            self.amount = 1.0
            # deliberately no `interval`

        def __getattr__(self, name):
            if name == "interval":
                return None
            raise AttributeError(name)

    bars = [_BarNoInterval(base_ts + datetime.timedelta(days=i)) for i in range(10)]
    adapter = real_adapter.RealKronosAdapter()
    eligible = Eligible(
        model_id="kronos_base", horizon_bars=5, context_length=512, unverified=True
    )
    from app.kronos.adapter import ConstraintSpecMissingError

    with pytest.raises(ConstraintSpecMissingError):
        adapter.predict(eligible, bars)


@pytest.mark.asyncio
async def test_real_adapter_tokenizer_shared_across_models(monkeypatch):
    """kronos_base + kronos_small share a tokenizer — load it once."""
    calls: list[str] = []

    class TrackingTokenizer(_FakeTokenizer):
        @classmethod
        def from_pretrained(cls, tokenizer_id):
            calls.append(tokenizer_id)
            return cls()

    monkeypatch.setattr(
        real_adapter,
        "_import_runtime",
        lambda: (_FakeModel, TrackingTokenizer, lambda model, tok, max_context: _FakePredictor()),
    )

    base_ts = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    bars = [
        _FakeBar(
            ts=base_ts + datetime.timedelta(days=i),
            open=1.0, high=1.0, low=1.0, close=1.0,
            volume=1.0, amount=1.0, interval="1d",
        )
        for i in range(450)
    ]
    adapter = real_adapter.RealKronosAdapter()

    for mid in ("kronos_base", "kronos_small"):
        adapter.predict(
            Eligible(model_id=mid, horizon_bars=5, context_length=512, unverified=True),
            bars,
        )

    # base + small both use Kronos-Tokenizer-base — only one load.
    assert calls.count("NeoQuasar/Kronos-Tokenizer-base") == 1
