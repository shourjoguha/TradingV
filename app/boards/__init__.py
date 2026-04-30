"""Boards — casual ticker lists ("Watchlists" in UI) — Phase MW-2.

Distinct from the operational ``watchlist`` table that drives Kronos
predictions. Boards are lightweight: one row per ticker per list, no
prediction work fired by membership. Quote data (last close + 1w Δ%)
lives on ``ticker_market_data`` so casual lists, Dashboard tiles, and
the sector drill-in all read from one source of truth.
"""
