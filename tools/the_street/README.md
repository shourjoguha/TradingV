# tools.the_street

Read-side CLI for the smart-money snapshots stored under
`<vault>/The Street/`. The vault-indexer handles semantic retrieval; this
CLI is for direct lookups by ticker, tier, or politician name when an exact
key is known.

## Quick reference

```bash
# Latest snapshot listings
python -m tools.the_street.query --list-snapshots

# Tier 1 of latest snapshot
python -m tools.the_street.query --tier 1

# Tier 2 of a specific date
python -m tools.the_street.query --tier 2 --date 2026-05-08

# Cross-snapshot ticker lookup
python -m tools.the_street.query --ticker META

# Politician's disclosures across snapshots
python -m tools.the_street.query --politician "Cleo Fields"

# JSON output for piping into another tool
python -m tools.the_street.query --tier 1 --json | jq '.rows[].ticker'
```

## Conventions

- `VAULT_PATH` env var overrides the default `~/Documents/knowledge-vault`.
- Date format is `YYYY-MM-DD` matching the snapshot directory.
- ETFs are excluded from tier listings by default. Pass `--include-etfs` to
  include them.
- Output is plain text by default for human reading; pass `--json` for
  machine consumption.

## What this CLI does NOT do

- It does not write. Snapshot generation is operator-driven (currently
  manual) per `<vault>/The Street/_README.md`.
- It does not query the Trailblazers / Billionaires JSON directly. Use the
  raw files in `<vault>/The Street/data/<date>/` if you need fund-level
  detail beyond the aggregate `multi-channel-tickers.tsv`.
- It does not cache. Each invocation re-reads the TSV/JSON.

## Library use

```python
from tools.the_street.query import (
    list_snapshots, latest_snapshot, find_ticker, list_tier, find_politician,
)

snap = latest_snapshot()
tier1 = list_tier(1, snap)
meta_history = find_ticker("META")
fields_buys = find_politician("Cleo Fields")
```
