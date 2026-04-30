"""Provider protocol — every macro source implements this."""
from __future__ import annotations

import datetime
from typing import List, Optional, Protocol, Tuple


class MacroProvider(Protocol):
    name: str

    async def fetch(
        self, symbol: str, since: Optional[datetime.date] = None
    ) -> List[Tuple[datetime.date, float]]:
        """Return (date, value) pairs sorted ascending. Empty list if
        upstream returned nothing or the symbol is unrecognised.

        Caller (service) handles upsert + dedup. Provider must NOT cache."""
        ...
