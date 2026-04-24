# Market data module (`app/market_data/`)

OHLCV fetch, cache, and query. Feeds Kronos in Phase 4.

## Schema — `ohlcv_bars`
Composite PK `(symbol, interval, ts)`. Columns: `open, high, low, close, volume, amount (nullable), provider, fetched_at`. Index `(symbol, interval, ts DESC)` for latest-N queries.

- `symbol` normalized uppercase.
- `interval` is the canonical code (see below), not the vendor's.
- `ts` is tz-aware UTC.
- `amount` = turnover (close × volume is an acceptable fallback when the provider doesn't report it). Kronos requires it; compute if missing before inference.

## Canonical intervals (`intervals.py`)
`1m, 5m, 15m, 30m, 1h, 1d, 1w`. Single source of truth. Providers map canonical → vendor code inside their own adapter. Callers and the `/v1/intervals` endpoint only ever see canonical strings.

## Provider contract (`providers/base.py`)
```python
class Provider(Protocol):
    name: str
    def supports(asset_class, interval) -> bool
    async def fetch_ohlcv(symbol, asset_class, interval, start, end) -> List[Bar]
```
- Returns `List[Bar]` in ascending `ts` order.
- Raises `UnsupportedRequest` when asset/interval combo not supported.
- No DB access — service layer handles caching.

### YFinanceProvider
- Stocks + ETFs only (crypto deferred).
- yfinance is sync + blocking; `asyncio.to_thread` wraps it.
- yfinance imposes max-range per interval; `_DEFAULT_RANGE_DAYS` is conservative. Widen when Kronos asks for more history.

## Registry (`registry.py`)
`resolve(asset_class, interval)` returns the first provider that `supports(...)`. Tests swap via `registry._PROVIDERS.clear(); registry.register(fake, prepend=True)`.

## Service flow
- `service.refresh(symbol, interval, …)` → auto-upsert ticker → resolve provider → fetch → UPSERT into `ohlcv_bars` (`ON CONFLICT DO UPDATE` on Postgres / `ON CONFLICT DO UPDATE` on SQLite).
- `service.get_cached(symbol, interval, limit)` → query most-recent N bars, return ascending.

Any `/v1/ohlcv` call with unknown symbol auto-registers it in `tickers` with `source=analysis`. Same as the Phase 4 analysis path will do.

## Endpoints
- `GET /v1/intervals` — canonical interval list. Not yet filtered by model eligibility (that's Phase 3).
- `GET /v1/ohlcv?symbol=&interval=&limit=&refresh=` — cache read + optional provider refresh. Errors: `400` unknown interval, `422` unsupported combo, `502` provider error.

## Known gaps / decisions
- No smart staleness detection yet — caller decides via `refresh=true`. Phase 3/4 may add "if latest ts < now - interval, auto-refresh" logic. Defer until it's a felt need.
- `amount` backfill (close × volume) is NOT done here — belongs in the Kronos adapter's data-prep step so the cache stays raw.
- Redis is the wrong tool for this cache — see `architecture.md` storage split.
