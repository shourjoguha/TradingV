"""Phase C2 — trading-day filter per asset class."""
from __future__ import annotations

import datetime

import pytest

from app.market_data.calendar import is_trading_day


# 2026-04-25 is Saturday, 2026-04-26 is Sunday, 2026-04-27 is Monday.
SAT = datetime.date(2026, 4, 25)
SUN = datetime.date(2026, 4, 26)
MON = datetime.date(2026, 4, 27)


@pytest.mark.parametrize(
    "ac,day,expected",
    [
        ("stock", MON, True),
        ("stock", SAT, False),
        ("stock", SUN, False),
        ("etf", SAT, False),
        ("forex", SAT, False),
        ("futures", SAT, False),
        ("crypto", SAT, True),
        ("crypto", SUN, True),
        ("commodity", SUN, True),
        # Unknown / None falls through permissively.
        ("unknown", SAT, True),
        ("", SAT, True),
        (None, SAT, True),
        # Case-insensitive.
        ("STOCK", SAT, False),
        ("Crypto", SAT, True),
    ],
)
def test_is_trading_day(ac, day, expected):
    assert is_trading_day(ac, day) == expected
