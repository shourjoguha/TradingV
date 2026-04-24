# Kronos

Guardrail layer around the Kronos candlestick models. Owns the registry, the validator, the adapter interface, and the vendored model code.

## Files
- `registry.yaml` — **hand-authored** model specs (reconciled against upstream code 2026-04-24).
- `registry.py` — parses YAML → frozen `ModelSpec` dataclasses. Cached.
- `schemas.py` — `Eligible` / `Ineligible(reason, message)` + `IneligibleReason` enum.
- `validator.py` — `EligibilityValidator.check(...)` — THE choke-point.
- `adapter.py` — `KronosAdapter` Protocol + `StubAdapter` (raises unless `DEBUG_STUB=true`).
- `real_adapter.py` — `RealKronosAdapter` — loads weights from HF, runs inference. Heavy deps (torch, huggingface_hub) imported lazily.
- `_vendor/kronos_model/` — vendored upstream `model/` dir. Do not edit. Re-copy from upstream to bump.
- `service.py` — `CACHE_FEATURES` constant.
- `routes.py` — `/v1/models`, `/v1/timeframes`, `/v1/eligibility`.

## Registry accuracy
Upstream source: https://github.com/shiyu-coder/Kronos.

Verified from upstream code:
- **Required columns**: only `['open', 'high', 'low', 'close']`. `volume` and `amount` are optional — Kronos auto-fills zeros (accuracy degrades without them).
- **max_context**: 512 for `kronos-base` and `kronos-small`, 2048 for `kronos-mini`.
- **Tokenizers**: `NeoQuasar/Kronos-Tokenizer-base` (base + small), `NeoQuasar/Kronos-Tokenizer-2k` (mini).
- **Timestamps required**: Kronos extracts `[minute, hour, weekday, day, month]` features.

Still conservative / unverified:
- Interval list. Code is sequence-agnostic. We allow `["5m","15m","30m","1h","1d","1w"]`; `1m` excluded (noisy, not in paper examples).
- Horizon upper bound. Autoregressive beyond `max_context` degrades. We cap `max_horizon_bars` well below.
- Asset-class mix. Paper: 45 global exchanges spanning stocks, ETFs, crypto — all allowed.

All entries keep `unverified: true` until user signs off per model.

## Guardrail rule (do not break)
`adapter.predict(...)` accepts ONLY an `Eligible`. Every call site goes through `EligibilityValidator.check(...)` first and pattern-matches the result. No bypass.

Rejection reasons are a closed enum — extend `IneligibleReason` if a new class is needed, never fall back to a generic string.

## Adapter selection
- **Default**: `StubAdapter`. Raises `NotImplementedError` unless `DEBUG_STUB=true` (then returns a synthetic forecast).
- **Production**: `RealKronosAdapter`. Activated at startup when `KRONOS_ENABLED=true`. Requires `requirements-kronos.txt` installed on the host.

First `predict(model_id)` call per process downloads weights from HF. Point `HF_HOME` at a persistent volume (Railway volume mount at `/data/hf-cache` is the plan) so restarts don't re-download.

## Routes
- `GET /v1/models?asset_class=&interval=` — registered models, optional filters.
- `GET /v1/timeframes?ticker=&model_id=` — intervals eligible for that (ticker, model). Drives dropdowns so unsupported combos are never exposed.
- `GET /v1/eligibility?model_id=&ticker=&interval=&horizon_bars=` — pre-flight check returning the same `Eligible | Ineligible(reason)` shape the orchestrator uses.

All `/v1/*` auth via `X-API-Key`.
