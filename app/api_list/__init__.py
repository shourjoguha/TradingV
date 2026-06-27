"""api_list — read-only catalog of TradingV's external data sources.

Surfaces two categories so the operator (and the frontend `/api-list` page) can
see what's wired and what's configured:
  1. OHLCV price providers registered in ``app/market_data/registry.py``.
  2. Agent data feeds (news/social/sentiment) consumed by the Agents lane.

Pure read-side: it reflects current config, it does not mutate the registry.
"""
