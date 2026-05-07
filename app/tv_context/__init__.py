"""TradingView context ingest layer.

Receives operator-curated signals (Pine webhook alerts, chart screenshots,
free-form notes, TV-Ideas posts, calendar events) into a single polymorphic
table. Surfaces them to research/ask + hypothesis-eval as retrieval-time
context. Expires per category default with per-row override; preserves a
tombstone summary indefinitely.

See ``.claude/tv_context.md`` for the module doc.
"""
