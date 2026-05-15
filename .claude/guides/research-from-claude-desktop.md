# Driving this app from Claude Desktop

> **Use when:** operator is in Claude Desktop (Max subscription) and wants to do research against the TradingView app's data + vault without burning Anthropic API credits.

The laptop runs three things side-by-side: backend (`localhost:8000`), vault indexers (`:8001` finance / `:8002` fitness / `:8003` nutrition), and Claude Desktop. **Primary access path is the globally-registered `1kb_Shos` MCP server**, which already exposes the app's Postgres + the vault as MCP tools. `curl` against the backend is a fallback for the handful of endpoints that do non-trivial computation.

## Why this exists (and why not OAuth)

Anthropic's 2025/2026 "OpenClaw ban" revoked the OAuth path for non-first-party clients; using a Pro/Max OAuth token inside this FastAPI app is a Consumer ToS violation. Claude Desktop **is** a first-party client — so we let Desktop query the local DB + vault directly. No tokens leave the laptop, no API charges accrue.

If `ANTHROPIC_API_KEY` is set in Desktop's process env, billing can silently fall through to the API. **Keep it unset.**

## 1. Bootstrap

```python
# In Claude Desktop:
mcp__1kb_Shos__sources()        # confirm tradingview ok + indexer :8001 ok
mcp__1kb_Shos__scope_get()      # should be "finance" (auto-set when cwd is under Claude/TradingView)
# If wrong: mcp__1kb_Shos__scope_set(scope="finance")
```

Healthy state: `sources["tradingview"].ok == true`, `sources["knowledge_vault"].endpoints.finance.ok == true`. If the indexer is down, semantic search degrades; DB queries still work. If `tradingview` is down, all SQL fails — operator runs `./run-dev.sh` from `/Users/shourjosmac/Documents/Claude/TradingView /`.

## 2. SQL recipes against `tradingview`

All queries: `mcp__1kb_Shos__db_query(source="tradingview", sql="...")`. Mutations rejected. Auto-LIMIT 1000. Statement timeout 5s. Column names verified against live schema 2026-05-14.

### At-risk hypotheses with last evaluation

```sql
SELECT
  h.slug, h.title, h.axis, h.claim_type, h.status,
  h.expires_at,
  e.status_after AS last_status_after,
  e.reason       AS last_reason,
  e.evaluated_at AS last_eval_at
FROM hypothesis h
LEFT JOIN LATERAL (
  SELECT status_after, reason, evaluated_at
  FROM hypothesis_evaluation
  WHERE hypothesis_id = h.id
  ORDER BY evaluated_at DESC LIMIT 1
) e ON TRUE
WHERE h.status = 'active'
  AND h.expires_at < NOW() + INTERVAL '30 days'
ORDER BY h.expires_at;
```

There is no `at_risk` column — that's computed (active + expiring < 30d).

### Open drift alerts

```sql
SELECT ticker, horizon_offset, model_id,
       recent_mape, all_time_mape, ratio,
       recent_sample_count, flagged_at
FROM drift_alerts
WHERE acknowledged_at IS NULL
ORDER BY ratio DESC;
```

### Recent MAPE for a (ticker, horizon)

```sql
SELECT made_on, target_date, predicted_close, actual_close,
       error_pct, abs_error_pct, direction_correct
FROM prediction_accuracy
WHERE ticker = 'AAPL' AND horizon_offset = 1
ORDER BY target_date DESC
LIMIT 60;
```

### Ticker review queue — surfaced rows (`times_seen >= 2`)

```sql
SELECT id, ticker, times_seen, channels, recent_caption_snippets,
       last_seen_at, previously_dismissed_at
FROM ticker_review_queue
WHERE status = 'pending' AND times_seen >= 2
ORDER BY last_seen_at DESC
LIMIT 50;
```

`channels` and `recent_caption_snippets` are JSON arrays — when summarising, render the most-recent-last entries.

### P&L attribution per opportunity rule

```sql
SELECT o.rule_label,
       COUNT(*)                AS n_trades,
       SUM(t.realized_pnl)     AS total_pnl,
       AVG(t.realized_pnl)     AS avg_pnl,
       SUM(CASE WHEN t.realized_pnl > 0 THEN 1 ELSE 0 END)::float / COUNT(*) AS hit_rate
FROM trades t
JOIN opportunities o ON t.opportunity_id = o.id
WHERE t.exit_at IS NOT NULL
GROUP BY o.rule_label
ORDER BY total_pnl;
```

US spelling: `realized_pnl`. Trade is closed when `exit_at IS NOT NULL`.

### Open opportunities by ticker

```sql
SELECT ticker, rule_label, predicted_move_pct, confidence,
       generated_at, expires_at
FROM opportunities
WHERE status = 'open' AND ticker = 'AAPL'
ORDER BY generated_at DESC;
```

### Pending research queries (top by score)

```sql
SELECT id, asked_at, query, status, score, is_deferred,
       hypothesis_ids
FROM research_queries
WHERE status = 'pending' AND is_deferred = FALSE
ORDER BY score DESC NULLS LAST
LIMIT 10;
```

`hypothesis_ids` is a JSON array; cross-ref to `hypothesis.id` for related hypothesis context.

### TV Context for a ticker

```sql
SELECT id, kind, captured_at, vault_path, payload
FROM tv_context_items
WHERE ticker = 'AAPL' AND status = 'active'
ORDER BY captured_at DESC
LIMIT 50;
```

For large screenshots: `heavy_blob_dropped = TRUE` means the image was stripped, but the vision summary in `payload` remains.

### Macro time series

```sql
SELECT date, value
FROM macro_series
WHERE symbol = '^VIX'
  AND date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY date;
```

### Earnings calendar (next 14 days, roster only)

```sql
SELECT ec.ticker, ec.expected_at, ec.confidence, ec.source
FROM earnings_calendar ec
JOIN watchlist w ON w.symbol = ec.ticker
WHERE ec.expected_at BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '14 days'
ORDER BY ec.expected_at;
```

### Watchlist + boards

```sql
-- Roster symbols
SELECT symbol, added_at, notes FROM watchlist ORDER BY symbol;

-- Boards with member counts
SELECT b.id, b.name, b.description, COUNT(bt.ticker) AS n_tickers
FROM boards b LEFT JOIN board_tickers bt ON bt.board_id = b.id
GROUP BY b.id, b.name, b.description
ORDER BY b.name;

-- Members of a specific board
SELECT ticker, notes, added_at
FROM board_tickers
WHERE board_id = '<board-uuid>'
ORDER BY added_at DESC;
```

## 3. Vault recipes against `knowledge_vault`

Prefer 1kb_Shos tools over `curl /v1/vault/*` — they go directly to the indexer and return more useful shapes.

```python
# Default: ranked chunks with full text inline (one call, no follow-up needed)
mcp__1kb_Shos__bundle(q="reshoring industrial policy", scope="finance", k=5)

# Long-doc paged read (video transcripts, snapshot index files):
mcp__1kb_Shos__node_chunks(
    path="Videos/click-capital/2026-05-08-AAPL.md",
    domain="finance",
    offset=0, limit=20,
)

# Cheap preview before committing to a full read:
mcp__1kb_Shos__outline(path="The Street/snapshots/2026-05-08/_index.md", domain="finance")

# Local subgraph (similarity neighbours + explicit edges):
mcp__1kb_Shos__traverse(path="Topics/_ticker-review-queue.md", domain="finance", depth=1)
```

### Vault paths worth knowing

| Path | Contents |
|---|---|
| `Videos/<channel-slug>/` | Auto-ingested video drafts |
| `Videos/<channel-slug>/_index.md` | Channel rolling table inside `<!-- AUTO:chart-references:start --> ... <!-- AUTO:chart-references:end -->` |
| `The Street/snapshots/<YYYY-MM-DD>/` | Tier-1/2/3, politicians, insiders, options — **vault-only, no Postgres table** |
| `The Street/snapshots/<YYYY-MM-DD>/_index.md` | Snapshot overview |
| `Research/<topic>.md` | Operator-written research notes |
| `Topics/_ticker-review-queue.md` | Sunday digest from Phase D |
| `Topics/_review-queue.md` | Research review queue digest |

**The Street has no Postgres table.** Always reach for it via `bundle()` or by reading the snapshot markdown directly.

## 4. Workflow recipes

Each = one operator question, one ordered tool chain.

### A. "What's drifting and worth attention?"

1. `db_query` open drift alerts (SQL §2).
2. For each `(ticker, horizon_offset)` worth drilling into, `db_query` `prediction_accuracy` for the last 60 days (SQL §2) — eyeball the trend.
3. If cohort math gets annoying (multi-ticker × multi-horizon comparisons): **fallback** `curl /v1/accuracy/grid?tickers=…&last_n=30` (see §6).
4. Synthesise: which alerts are persistent vs self-resolving. Recommend acknowledgement only for persistent.

### B. "What hypotheses are at risk?"

1. `db_query` at-risk hypotheses + last evaluation (SQL §2).
2. For each at-risk: `bundle(q="<slug or title>", scope="finance", k=5)` — vault evidence (operator notes, video chart refs).
3. `db_query` pending research queries (SQL §2) — cross-ref `hypothesis_ids` JSON to the at-risk set; flag at-risk hypotheses with no queued stress-test.
4. Synthesise per-hypothesis: what's failing (evaluation `reason`) + what's queued.

### C. "What did videos show this week?"

1. `bundle(q="chart references this week", scope="finance", k=8)` — surfaces channel `_index.md` blocks + recent drafts.
2. For each channel hit: `outline(path="Videos/<channel>/_index.md", domain="finance")` → drill the rolling-references table.
3. For tickers mentioned: `db_query` `tv_context_items` for related screenshots/alerts (SQL §2) + `db_query` `ticker_review_queue` to see if they're already in the operator's universe.
4. Synthesise: which tickers showed up in multiple channels, which are net-new (in `ticker_review_queue.pending`), which the operator already holds (watchlist/boards).

### D. "How are my trades attributing to my opportunity rules?"

1. `db_query` P&L by rule (SQL §2).
2. For the worst rule: `db_query` closed opportunities matching that label + their source predictions to see whether predictions were right but rule fired badly.
3. Synthesise: rule X is leaking because (prediction quality / horizon mismatch / threshold drift). Recommend retire vs adjust — but **don't act**, send operator to web UI.

### E. "What new tickers do I keep seeing but haven't tracked?"

1. `db_query` ticker_review_queue surfaced rows (SQL §2).
2. For each, look at `channels` + `recent_caption_snippets` JSON for context.
3. Optionally `node_chunks(path="Topics/_ticker-review-queue.md", domain="finance")` for the Sunday rollup if you want narrative framing.
4. Synthesise: rank by `times_seen × channel diversity`. Recommend per-row add-to-roster / add-to-board / dismiss — operator does the resolve in the web UI at `localhost:3000/today`.

## 5. Cross-table aggregations (hand-rolled when you need them)

The schemas above unlock a lot of joins not exposed by the backend. Examples:

```sql
-- Hypotheses with TV Context links + last screenshot per ticker
SELECT h.slug, h.title,
       COUNT(DISTINCT t.ticker) AS n_tickers,
       MAX(t.captured_at)       AS last_screenshot_at
FROM hypothesis h
JOIN hypothesis_tv_context_links htl ON htl.hypothesis_id = h.id
JOIN tv_context_items t            ON t.id = htl.tv_context_id
WHERE h.status = 'active'
GROUP BY h.slug, h.title
ORDER BY last_screenshot_at DESC NULLS LAST;
```

```sql
-- Tickers showing up in BOTH the review queue and recent TV Context
SELECT r.ticker, r.times_seen, COUNT(t.id) AS tv_context_count
FROM ticker_review_queue r
LEFT JOIN tv_context_items t
  ON t.ticker = r.ticker AND t.captured_at > NOW() - INTERVAL '14 days'
WHERE r.status = 'pending' AND r.times_seen >= 2
GROUP BY r.ticker, r.times_seen
ORDER BY r.times_seen DESC;
```

If a recipe needs this kind of cross-table view repeatedly, the right move is a Postgres VIEW that `db_query` can `SELECT * FROM` — **not** a new MCP server.

## 6. Curl fallback (backend HTTP)

Use ONLY for endpoints whose computation isn't a clean SQL query.

```bash
export API_KEY=$(grep '^API_KEY=' "/Users/shourjosmac/Documents/Claude/TradingView /.env.laptop" | cut -d= -f2-)
export BACKEND=http://localhost:8000
H="X-API-Key: $API_KEY"
```

| Path | Use when |
|---|---|
| `GET /v1/accuracy/grid?tickers=<csv>&last_n=<N>` | Per-(ticker, horizon) MAPE cohort grid — backend does the binning |
| `GET /v1/accuracy/pair?ticker=<sym>&horizon_offset=<N>` | Drilldown with bucket rollups |
| `GET /v1/market-data/quotes?symbols=<csv>` | Live yfinance quotes — not in DB until next OHLCV tick |
| `GET /v1/the-street/digest/<date>/<sym>` | Pre-baked operator-friendly digest text |
| `GET /v1/trades/pnl/by-rule` | Same numbers as the SQL above, but with rule_label expansion via `app.opportunities.rules` |

Skip everything else — SQL or vault tools beat curl.

**Never** call `POST /v1/research/ask` — that runs the backend's Anthropic SDK and re-bills the API key.

## 7. Guardrails

- **Read-only.** 1kb_Shos rejects `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`. The curl fallback list contains only GETs. To act on a finding (add a ticker, dismiss a review entry, approve a research query), tell the operator to use `localhost:3000`.
- **`ANTHROPIC_API_KEY` stays unset** in Desktop's process env.
- **Prefer `db_query` over curl** when both can answer. SQL is faster, no backend dependency.
- **Prefer Read of a known vault path** over `bundle` / `search` when you already know the file path (no re-tokenisation of chunk metadata).
- **Demo discipline.** This playbook is operator-personal-use; nothing in here ships to demo / Railway.

## 8. Gotchas

- **Auto-LIMIT 1000** on `db_query` — for >1000 rows, paginate via `OFFSET`, or add an explicit `LIMIT` with a tighter where-clause.
- **5s statement timeout** — heavy joins on `prediction_points` × `ohlcv_bars` may hit it; constrain by `ticker` + date range.
- **`scope_set("finance")`** must be active for `tradingview` to be reachable on some setups. Run `scope_get()` first if SQL errors out.
- **No `the_street_*` Postgres table.** All of "The Street" lives in the vault. Use `bundle()` against snapshots.
- **`hypothesis_evaluation` has no `verdict` column** — use `status_after` + `reason`. The "verdict" the UI shows on the Research page comes from `research_queries.verdict`.
- **`/v1/ticker-review/queue` may 404** if the backend was started before Phase D shipped (2026-05-14). Operator restart fixes it; SQL via `db_query` works regardless.
- **Indexer health** — if `bundle()` fails, `mcp__1kb_Shos__sources()` shows `:8001` status. Indexer is laptop-only.

## 9. When to upgrade

If a recipe needs cross-table aggregation that hits the 5s timeout, the right answer is a **Postgres VIEW** that `db_query` can `SELECT * FROM` — not a custom MCP server. 1kb_Shos already IS the custom MCP; building another duplicates work.

If a recipe needs **write actions** (add to roster, dismiss review entry, approve research query), that's a different design — would need a confirm-modal pattern and operator review per action. Out of scope for this playbook; operator writes in the web UI.

## See also

- [glossary.md](glossary.md) — rule label expansion (R1 → "BUY +2% over 5d (HR≥60%)") and status enum definitions
- [recipes.md](recipes.md) — backend-side recipes (different audience: code authors adding to the app)
- [../modules/README.md](../modules/README.md) — per-module deep-dives; drill in when an endpoint's behaviour is unclear
- `~/.claude/kb-overview.md` — auto-generated 1kb_Shos catalogue (always in session context)
- [../../tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md](../../tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md) — finance/fitness/nutrition domain rules
- [../../use_me_guide.md](../../use_me_guide.md) §1.5 — vault indexer operator runbook
