# Module docs

One file per `app/<module>/` package. Each describes the module's purpose,
schema, key endpoints, decisions that aren't obvious from code, and known
gaps. Read one of these when you're touching that module's code.

## Index

| Module | Doc | Touches |
|---|---|---|
| `app/core/` | [core.md](core.md) | config, db engine, auth |
| `app/alerts/` | [alerts.md](alerts.md) | TradingView webhook ingest, `/webhook` |
| `app/tickers/` | [tickers.md](tickers.md) | global symbol registry, `/v1/tickers` |
| `app/market_data/` | [market_data.md](market_data.md) | OHLCV cache, `/v1/ohlcv`, `/v1/intervals`, providers |
| `app/kronos/` | [kronos.md](kronos.md) | model registry, validator, `/v1/models` + `/v1/timeframes` + `/v1/eligibility` |
| `app/analysis/` | [analysis.md](analysis.md) | job orchestrator, fan-out, `/v1/analysis/*` |
| `app/queue/` | [queue.md](queue.md) | submit queue + single-flight worker |
| `app/sync/` | [sync.md](sync.md) | outbox replication, peer push, dual-backend |
| `app/watchlist/` | [watchlist.md](watchlist.md) | operational roster, daily-run target set |
| `app/schedule/` | [schedule.md](schedule.md) | daily forecast runner |
| `app/predictions/` | [predictions.md](predictions.md) | `prediction_points`, by-target, by-horizon |
| `app/accuracy/` | [accuracy.md](accuracy.md) | `prediction_accuracy`, `drift_alerts`, evaluator |
| `app/opportunities/` | [opportunities.md](opportunities.md) | rule engine, signal generator |
| `app/trades/` | [trades.md](trades.md) | manual trade journal, P&L attribution |
| `app/macro/` | [macro.md](macro.md) | `macro_series`, yfinance + FRED ingestion, ratios |
| `app/boards/` | [boards.md](boards.md) | "Watchlists" UI, casual ticker lists |
| `app/hypotheses/` | [hypotheses.md](hypotheses.md) | `hypothesis` + `hypothesis_evaluation`, invalidator DSL |
| `app/views/` | [views.md](views.md) | markdown view registry |
| `app/research/` | [research.md](research.md) | `research_queries`, stress-test answers |
| `app/tv_context/` | [tv_context.md](tv_context.md) | `tv_context_items`, screenshots, vision summaries |
| `app/notifications/` | [notifications.md](notifications.md) | Telegram notifier, drift alerts, daily digest |
| `app/labels/` | [labels.md](labels.md) | free-form ticker metadata |
| `app/admin/` | [admin.md](admin.md) | loop registry, `app_settings`, `process_status`, kill-switch |
| `app/earnings/` | [earnings.md](earnings.md) | `earnings_calendar`, IR-channel trigger gate |
| Vault (Obsidian + indexer) | [vault.md](vault.md) | knowledge layer + `tools/vault_indexer/` sidecar |

## Conventions

Every module doc follows the same shape:

1. **One-line purpose**
2. **Schema** — tables, columns, key indices
3. **Endpoints** — paths + brief behaviour
4. **Decisions that aren't obvious from code** — load-bearing trade-offs, link to ADRs in [`../decisions/`](../decisions/) when applicable
5. **Known gaps / future work** — link to [`../status/backlog.md`](../status/backlog.md) or [`../status/tech_debt.md`](../status/tech_debt.md)

When adding a new module:
- Mirror an existing doc that's closest in shape
- Register the new doc in this README's index table
- Add a row to [`../../CLAUDE.md`](../../CLAUDE.md) so the agent's reading path stays accurate

## See also

- [`../guides/architecture.md`](../guides/architecture.md) — top-of-stack module map
- [`../guides/recipes.md`](../guides/recipes.md) — how to add a feature that touches several modules
- [`../decisions/`](../decisions/) — ADRs explaining "why" choices
