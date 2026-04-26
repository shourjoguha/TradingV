"""Trading-day predicate per asset class.

The schedule runner uses this to partition the watchlist on each tick:
- Stocks / ETFs / forex: Mon-Fri only.
- Crypto: 24/7 (always trading).
- Unknown: be permissive — fall through as 'always trading' so we don't
  silently drop a poorly-classified ticker on weekends.

Holiday calendars (e.g. NYSE) are out of scope for v1 — adding them is a
straightforward next step (e.g. ``pandas_market_calendars``) but isn't
required for the operator's first run.
"""
from __future__ import annotations

import datetime

# Asset classes that trade only on weekdays (Mon-Fri).
_WEEKDAY_ONLY = {"stock", "etf", "forex", "futures"}

# Asset classes that trade every day, including weekends.
_ALWAYS = {"crypto", "commodity"}


def is_trading_day(asset_class: str | None, day: datetime.date) -> bool:
    """Return True iff ``day`` is a trading day for ``asset_class``.

    Decision tree:
    - Crypto / commodity → always True.
    - Stock / ETF / forex / futures → Mon-Fri (Python ``weekday() < 5``).
    - Anything else (None, "unknown", brand-new label) → always True;
      we'd rather predict on a weekend and have the actual show null
      than silently skip an unclassified ticker.
    """
    if not asset_class:
        return True
    asset_class = asset_class.lower().strip()
    if asset_class in _ALWAYS:
        return True
    if asset_class in _WEEKDAY_ONLY:
        return day.weekday() < 5
    return True
