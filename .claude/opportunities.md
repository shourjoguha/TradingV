# Opportunities (signal generator)

Phase 3 of the trust-sprint roadmap. Bridges raw predictions → actionable BUY/SELL signals with provenance + lifecycle. Predicate on Phase 1 (accuracy data) — confidence = historical hit-rate for the (ticker, horizon, model) pair.

## Schema

`opportunities` (one row per (prediction, rule) hit):
```
id PK,
ticker, kind ENUM('buy'|'sell'),
generated_at,
source_prediction_id FK→prediction_points (CASCADE),
source_model_id,
rule_id, rule_label,
predicted_move_pct, confidence,        -- both 0..1; confidence = hit-rate at gen time
status ENUM('open'|'acted'|'expired'|'dismissed') DEFAULT 'open',
expires_at,                            -- = target_date + 1 day
acted_at, dismissed_at, dismissed_reason,

UNIQUE(source_prediction_id, rule_id)  -- idempotency
```

## Rule engine

Hardcoded rules in `app/opportunities/rules.py` (NOT a DSL — keep small until tunable thresholds prove useful):

| Rule | Trigger | Min hit-rate | Min samples |
|---|---|---|---|
| `R1` BUY +2% over 5d | predicted_move ≥ +2% AND horizon = 5 | ≥ 60% | ≥ 10 |
| `R2` SELL -2% over 5d | predicted_move ≤ -2% AND horizon = 5 | ≥ 60% | ≥ 10 |
| `R3` BUY +5% over 10d | predicted_move ≥ +5% AND horizon = 10 | ≥ 55% | ≥ 10 |

Each rule returns `RuleHit | None`. Generator runs all rules over each prediction; non-None hits become `Opportunity` rows. Confidence = the `hit_rate` value supplied by the input.

To tune: edit thresholds in `rules.py` and redeploy. To add a rule: add a function with the same `RuleInput → Optional[RuleHit]` signature, append to `RULES` list. To change to a DSL: do it only after thresholds have been hand-tuned for ≥ 2 weeks.

## Generator + lifecycle

`app/opportunities/service.py`:
- `generate_for_predictions(since=, limit=1000)` — scans recent `prediction_points`, fetches baseline + hit-rate, runs all rules, inserts `Opportunity` rows. Idempotent via `UNIQUE(prediction, rule)`. Returns `{scanned, evaluated, created, skipped_no_baseline}`.
- `expire_stale(now=)` — sweeps open opportunities past `expires_at` → status='expired'.
- `list_opportunities(status=, ticker=, limit=)` / `update_status(opportunity_id, status, dismissed_reason=)`.

Lifespan loop `_opps_loop()` in `app/main.py` ticks hourly: generate then expire.

## Endpoints

```
GET    /v1/opportunities?status=&ticker=&limit=        list (filter)
POST   /v1/opportunities/generate?since_hours=24       manual rule-engine run
POST   /v1/opportunities/expire                        manual sweep
PATCH  /v1/opportunities/{id} body={status, dismissed_reason}
```

## Files

- `app/opportunities/models.py` — `Opportunity` SQLAlchemy model
- `app/opportunities/rules.py` — `RuleInput`, `RuleHit`, `RULES` list, `evaluate(inp)`
- `app/opportunities/service.py` — generator, expiry, CRUD
- `app/opportunities/routes.py` — endpoints
- `migrations/versions/0014_opportunities.py`

## Frontend

`/opportunities` page: tabs (open/acted/dismissed/expired). Open tab shows action buttons:
- **Acted** → marks status, optionally jumps to `/trades?from=<oppId>` to log a trade with prefilled fields (links the trade to the opportunity for per-rule P&L attribution — see [trades.md](trades.md)).
- **Dismiss** → modal with optional reason text.

Color-coded predicted move (green up, red down), confidence as %, generated/expires timestamps.

## Why hardcoded rules + idempotency

- The rules don't need flexibility yet — three or four lines covers the common cases. A DSL is a footgun before you know what you're tuning.
- `UNIQUE(prediction, rule)` means the generator is safe to over-run. Re-running after a deploy or manual trigger never duplicates.

## Known gaps

- Per-rule P&L attribution exists ([trades.md](trades.md)) but only meaningful once trades start being logged against opportunities.
- Confidence is a snapshot of hit-rate at generation time — it doesn't update as the (ticker, horizon, model) accuracy changes. By design: an opportunity reflects the conviction the system had when it fired.
