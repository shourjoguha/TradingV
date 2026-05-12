# Decisions (ADRs)

Architecture Decision Records — one file per significant choice, with the why and the trigger to revisit. Use [000-template.md](000-template.md) when adding new ones.

## Index

| # | Title | Date | Status |
|---|---|---|---|
| 001 | [CF Pages over Lovable for cloud frontend hosting](001-cf-pages-over-lovable.md) | 2026-04-27 | Accepted |
| 002 | [Bidirectional sync via Tailscale (Railway → laptop)](002-bidirectional-sync-via-tailscale.md) | 2026-04-26 | Accepted |
| 003 | [Tier-1 in-process queue over Tier-2 (Redis + arq)](003-tier-1-queue-over-tier-2.md) | 2026-04-27 | Accepted |
| 004 | [Neumorphism (Soft UI) design system](004-neumorphism-design-system.md) | 2026-04-27 | Accepted |
| 005 | [Compact-neumorphic density (and 3 paired sub-decisions)](005-compact-neumorphic-density.md) | 2026-04-27 | Accepted |
| 006 | [Telegram only (no email/Slack/push API)](006-telegram-only-notification-channel.md) | 2026-04-27 | Accepted |
| 007 | [Hardcoded opportunity rules over a DSL](007-hardcoded-opportunity-rules-over-dsl.md) | 2026-04-27 | Accepted |
| 008 | [Postgres for everything durable; no Redis yet](008-postgres-only-no-redis-yet.md) | ongoing | Accepted |
| 009 | [Light-only frontend; no dark mode](009-light-only-no-dark-mode.md) | 2026-04-27 | Accepted |
| 010 | [Self-healing OHLCV fetch via the accuracy evaluator](010-self-healing-ohlcv-fetch.md) | 2026-04-30 | Accepted |
| 011 | [Choke-point recompute for scheduler mid-tick PUT race](011-schedule-mid-tick-put-race.md) | 2026-04-30 | Accepted |
| 012 | [Separate `macro_series` table over reusing `ohlcv_bars`](012-macro-workbench-storage-shape.md) | 2026-04-30 | Accepted |
| 013 | [Hypothesis object — schema, DSL, cascade timing, ship-shape](013-hypothesis-object.md) | 2026-05-01 | Accepted |
| 014 | [Vault-indexer — substrate, storage, embedder, authoring discipline](014-vault-indexer.md) | 2026-05-02 | Accepted |
| 015 | [Research stress-test endpoint — Phase 3](015-research-stress-test.md) | 2026-05-02 | Accepted |
| 016 | [TV Context — no browser automation, webhook-first](016-tv-context-no-browser-automation.md) | 2026-05-04 | Accepted |
| 017 | [TV Context vision — default ON for screenshot ingest](017-tv-context-vision-default-on.md) | 2026-05-04 | Accepted |

## How to add a new ADR

1. Copy [000-template.md](000-template.md) → next sequential number.
2. Fill in: context, options considered, decision, trigger to revisit, files affected, cross-references.
3. Add the row to the index above.
4. Cross-link from the affected module doc.

## When to add an ADR vs a backlog/tech_debt entry

- **ADR** (this folder) — a decision that shapes design or trade-offs (we picked X over Y for these reasons).
- **[backlog](../status/backlog.md)** — a feature deferred for product reasons.
- **[tech_debt](../status/tech_debt.md)** — code cruft we knowingly left behind.

These overlap. When in doubt: if you're choosing between options, ADR. If you're deciding to NOT do something, backlog or tech_debt.

## See also

- [`../guides/principles.md`](../guides/principles.md) — north-star principles that ADRs reference
- [`../status/`](../status/) — living state (roadmap / backlog / tech debt)
- [`../plans/`](../plans/) — phase plans where ADRs often originate
- [`../../CLAUDE.md`](../../CLAUDE.md) — top-level reading paths
