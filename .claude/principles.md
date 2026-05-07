# Principles + active trade-offs + implicit assumptions

Read this BEFORE making architectural changes. The other docs describe *what* the system is; this one describes *why* it is that shape and *what we're refusing to do*.

If you're tempted to violate one of these, ask first.

---

## Guiding principles (derived from the code, not aspirational)

1. **One operator. Forever.** Every module assumes a single user with a single API key. No tenancy, no permissions, no per-user state, no soft-delete, no audit log. This isn't documented elsewhere but it's load-bearing — it's why we have no auth beyond `X-API-Key`.

2. **Cheap reversibility.** Every phase tagged in git, snapshot before destructive change, rollback procedure committed. ~30 min/phase of process overhead in exchange for a "back out" door that always works. See `backups/ROLLBACK.md`.

3. **Belt-and-braces over surgical removal.** Concurrency gate kept after queue. Schedule_config columns kept after refactor. Old API response fields stay nullable. New code paths land before old ones are removed. Slower cleanup, lower regression risk. Removed entries land in [tech_debt.md](tech_debt.md) for periodic harvest.

4. **Compact docs over exhaustive.** Each `.claude/*.md` is < 1 screen by design (~75 lines avg). 31 docs, ~2300 lines total. Cross-file navigation cost is accepted; per-file grok cost is minimized.

5. **Postgres for everything durable.** No Redis (yet), no S3, no in-memory caches that matter. Slower than purpose-built tools at scale; trivially debuggable today. See storage split in [architecture.md](architecture.md).

6. **Inline lifespan tasks over external workers.** 11 background loops live in `app/main.py`. No celery, no arq, no separate worker process. One Python process per backend; boot semantics obvious; failure mode is "anything kills lifespan → everything dies together."

7. **Defensive defaults at every boundary.** Telegram no-op when unconfigured. yfinance failures logged and skipped. OHLCV refresh best-effort. Drift detector swallows exceptions. Stays alive at the cost of sometimes masking real failures (see "Trade-off: alert observability").

8. **Trust the model before trusting the trader.** Phase 1 (accuracy + drift) gates Phase 3 (opportunities). We'd rather know Kronos is wrong than build features that assume it's right. See [roadmap-shipped.md](roadmap-shipped.md) for the sequencing.

9. **Measure everything, alert on almost nothing.** 5 observability tables (`prediction_accuracy`, `drift_alerts`, `opportunities`, `trades`, `submit_queue`); 1 alert channel (Telegram, currently dormant). Stage-appropriate; will rebalance once signal-to-noise of alerts is provable.

10. **Ergonomics for the operator, not future users.** Every UX decision optimized for "what would the operator find readable." Compact-neumorphic, dense tables, terse error toasts, no onboarding flow. The day there's a second user, this assumption shatters.

---

## Active trade-offs (the things we've explicitly chosen NOT to do)

Each row: what we picked → what we paid for it → where the escape hatch is documented (so the reverse path is known).

| Picked | Paid | Escape hatch |
|---|---|---|
| Single-user simplicity | No path to share with another human without rewrite | None — this is the founding assumption |
| Postgres-only durability | Throughput at >10× scale | [tech_debt.md](tech_debt.md) "Tier 2 queue (Redis + arq)" |
| In-process workers | Multi-machine resilience (laptop dies → manual restart) | [tech_debt.md](tech_debt.md) Tier-2 path |
| Compact docs | No unified "what is this app" intro until [CLAUDE.md](../CLAUDE.md) elevator pitch ships | This file + CLAUDE.md elevator pitch |
| Pragmatic testing (mostly backend, 269 tests) | UI bugs only caught at preview/manual | [backlog.md](backlog.md) — would add Playwright E2E only when scale forces |
| Desktop-first frontend | Mobile is via Telegram only (no PWA, no responsive polish) | Mobile hamburger nav added in neumorphism redesign |
| Belt-and-braces | Code surface bloats over time | Monthly review of [tech_debt.md](tech_debt.md) |
| Telegram only | No email, no Slack, no push API redundancy | [roadmap-shipped.md](roadmap-shipped.md) Phase 4 — multi-channel deferred until Telegram proves valuable |
| Tailscale-only laptop | Public-internet laptop access requires a different tunnel | [backlog.md](backlog.md) "Public tunnel for laptop" |
| Hardcoded opportunity rules | Tunable strategies require redeploy | [opportunities.md](opportunities.md) — DSL deferred until thresholds proven |
| Compact-neumorphic density | No "airy" hero pages | The neumorphism design system locked this in deliberately |
| Build-time `VITE_*` env vars | Runtime config flexibility (env change → rebuild) | None — Vite-fundamental; live with it |
| Hardcoded ADRs in chat history (until now) | Loss when chat is archived | This file + [decisions/](decisions/) |

---

## Implicit assumptions (load-bearing, never previously written)

If any of these change, large parts of the system need re-thought.

- **Single user, single API key.** No multi-tenancy; no roles; no audit log.
- **Stocks/ETFs + crypto only.** Fixed income, FX-only-pairs, futures, options-as-primary not supported. Validators + asset_class enum assume this set.
- **Daily cadence is primary.** Intraday (5m, 1h) is supported but not optimized — schedule runs once/day; opportunity rules trigger off daily horizons.
- **Operator runs laptop most days.** Railway is a fallback replica, not the primary inference path. `RAILWAY_FALLBACK_ENABLED` is opt-in for that reason.
- **Background loops run on laptop only.** Lifespan in `app/main.py` gates 9 loops (accuracy_evaluator, drift_detector, digest, market_data, opps, macro, hyp_tick, research_weekly, queue_worker) by `INSTANCE_NAME != 'railway'`. Railway runs only `outbox-purge` and tv_context expire (daily). Reason: Railway is serverless — every self-wake is billable. Loops are laptop-primary computations anyway (vault on laptop, Kronos on laptop, Telegram dedupe risk).
- **Sync drain is batched, not per-job.** `SYNC_DRAIN_INTERVAL_SECONDS=300` (5 min) on laptop. Outbox enqueues are unchanged — semantic is "eventual consistency, ≤5 min latency."
- **Operator reads English. Times are UTC-internal, local-display.** All UI dates do `toLocaleString()` at render; backend stores UTC.
- **Bandwidth is unlimited; page weight isn't a hard constraint.** Vite + TS strict + Plus Jakarta + DM Sans webfonts ship at ~620 KB. Acceptable.
- **Network latency operator → Railway is ~100ms.** US/EU operator. Calls don't need batching.
- **Postgres is fast enough until queue depth > 5 OR row count > 1M per table.** Below those thresholds we don't optimize. Above, see Tier-2 queue + Redis caches.
- **Kronos CPU inference takes ~15-30s per (ticker, interval) on M3.** Worker single-flight is fine; multi-worker would OOM Railway free tier.
- **Telegram is the operator's primary mobile-push channel.** Any feature that needs mobile awareness routes through `app/notifications/telegram.py`.
- **CF Pages bundle hash + Railway commit SHA are sufficient as deployment versions.** No SemVer, no changelog auto-gen.

---

## Where to go next

- [architecture.md](architecture.md) — system map (modules, lifespan, sync, CORS).
- [tech_debt.md](tech_debt.md) — code cruft we deliberately left, with eviction triggers.
- [backlog.md](backlog.md) — features deferred for product reasons.
- [decisions/](decisions/) — per-decision ADRs (why we chose X over Y).
- [recipes.md](recipes.md) — how-to patterns for common changes.
- [glossary.md](glossary.md) — terminology used throughout.
