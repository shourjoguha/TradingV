"""Asset class inference from ticker symbol.

Heuristic only — user may override via PATCH /v1/tickers/{symbol}.
"""
from __future__ import annotations

# Common ETF suffixes / known ETF families. Not exhaustive.
_KNOWN_ETFS = {
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO", "VUG", "VTV",
    "XLF", "XLE", "XLK", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLC", "XLRE",
    "ARKK", "ARKG", "ARKW", "ARKQ", "ARKF",
    "GLD", "SLV", "TLT", "HYG", "LQD", "AGG", "BND",
    "EEM", "EFA", "FXI", "EWJ", "EWZ",
    "TQQQ", "SQQQ", "SOXL", "SOXS", "UPRO", "SPXL", "SPXS",
}

_CRYPTO_QUOTE_SUFFIXES = ("USDT", "USDC", "BUSD", "BTC", "ETH")
_CRYPTO_DASH_SUFFIXES = ("-USD", "-USDT", "-USDC")


def infer_asset_class(symbol: str) -> str:
    """Return 'crypto', 'etf', or 'stock'. Deterministic, case-insensitive."""
    if not symbol:
        return "stock"
    s = symbol.upper().strip()

    # Dash notation: BTC-USD, ETH-USD
    for suf in _CRYPTO_DASH_SUFFIXES:
        if s.endswith(suf):
            return "crypto"

    # Known ETF list
    if s in _KNOWN_ETFS:
        return "etf"

    # Concatenated quote pairs: BTCUSDT, ETHUSDC
    if len(s) > 4:
        for suf in _CRYPTO_QUOTE_SUFFIXES:
            if s.endswith(suf) and len(s) - len(suf) >= 2:
                # Avoid false positive on short tickers ending in 'ETH' like 'NETH' (no real case, safe guard)
                return "crypto"

    return "stock"
