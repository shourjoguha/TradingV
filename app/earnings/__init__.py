"""Earnings calendar — Phase 2 of the cost-aware iteration plan.

Refreshes the union of roster + The Street top-tier tickers from yfinance
(primary) + NASDAQ (fallback). Confirms with SEC EDGAR 8-K Item 2.02 once
filed. Capped at 150 tickers, 90-day TTL after last appearance.

Backs the trigger-window check in the IR YouTube channel poller so we
only transcribe earnings calls on the day they're released.
"""
