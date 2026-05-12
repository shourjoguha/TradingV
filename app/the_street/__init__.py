"""The Street — read-only HTTP surface over smart-money snapshots.

Wraps :mod:`tools.the_street.query` for consumption by the frontend Ticker Hub
and ``/the-street`` page. Pure read; no DB writes. Periodic-update pipeline
remains FUTURE WORK (see ``<vault>/The Street/_README.md``).
"""
