# Guides

Cross-cutting how-to and reference material that doesn't belong to a single
`app/<module>/` package. Read one of these when the work spans modules,
infra, or process.

## Index

| Guide | When to read |
|---|---|
| [architecture.md](architecture.md) | Top-of-stack system map. Read first when onboarding. Module list, daily-forecast pipeline, dual-backend topology, in-process schedulers. |
| [principles.md](principles.md) | Load-bearing decisions + active trade-offs + implicit assumptions. **Read before any architectural change.** |
| [glossary.md](glossary.md) | Terms used across docs and code (regime, drift, hit-rate, invalidator, etc.). |
| [recipes.md](recipes.md) | Cookbook: "how do I add an endpoint", "how do I wire a new lifespan loop", "how do I connect a new provider". |
| [testing.md](testing.md) | Test patterns + fixtures + how to run pytest cleanly (`unset API_KEY DATABASE_URL`). |
| [migrations.md](migrations.md) | Alembic conventions, when to write a migration, the `create_all` race, downgrade paths. |
| [railway-deployment.md](railway-deployment.md) | Railway entry points, env vars, Tailscale tunnel, Postgres backup. |
| [laptop-setup.md](laptop-setup.md) | Dev environment on the M3 MacBook (the primary backend). |

## When you need an ADR vs a guide

- ADR (`../decisions/`) — captures **why** a specific tradeoff was made at a point in time. Immutable once shipped.
- Guide (this folder) — captures **how** to work productively now. Updated as the codebase evolves.

When a guide and an ADR disagree, the ADR wins for "why we did X" historical context; the guide wins for "what's true today."

## See also

- [`../modules/`](../modules/) — per-module docs (mirror of `app/<module>/`)
- [`../status/`](../status/) — living state (roadmap, backlog, tech debt)
- [`../decisions/`](../decisions/) — ADRs
- [`../frontend/`](../frontend/) — frontend-specific guides
- [`../../CLAUDE.md`](../../CLAUDE.md) — entry point with reading paths by job
