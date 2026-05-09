# Demo bake scripts

Run from this worktree (`TradingView-demo/`). Uses the laptop's live
Postgres in **read-only** intent — never writes back. Output goes to
`demo-data/` which is committed to the `demo` branch.

## Bake a fresh snapshot

```bash
# Activate the laptop venv (it has sqlalchemy + asyncpg + aiosqlite installed)
source "../TradingView /venv/bin/activate"

# Point at the laptop Postgres (same URL the live app uses)
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5439/tradingview"
export DEMO_CUTOFF_DATE=$(date +%F)

python scripts/bake_demo_snapshot.py

# Inspect output
git diff --stat demo-data/
git add demo-data
git commit -m "demo: refresh snapshot $DEMO_CUTOFF_DATE"
git push origin demo
```

## What gets scrubbed

- Columns named `email`, `ip`, `ip_address`, `user_agent`, `raw_prompt`, `raw_response`, `session_id` are dropped.
- Adjust `SCRUB_COLS` and `_scrub_row` in `bake_demo_snapshot.py` if your schema has other PII.

## Adjusting queries

The queries assume table/column names from the live laptop schema. If
the bake fails with `column "..." does not exist`, edit the relevant
`Q_*` constant in `bake_demo_snapshot.py` to match.

The placeholder JSONs in `demo-data/` already produce a working demo —
the bake is **non-blocking**. Ship the demo with placeholders, replace
later when ready.
