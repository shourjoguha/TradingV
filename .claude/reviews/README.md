# Reviews

Periodic architecture / data / external-pattern reviews. Each is
date-stamped and self-contained. Reviews capture **point-in-time
analysis** — read them for "how did things look in May 2026", not for
current state (use [`../guides/architecture.md`](../guides/architecture.md)
or [`../status/`](../status/) for that).

## Index

| Review | Focus | Output |
|---|---|---|
| [2026-05-02-data-and-models-architecture.md](2026-05-02-data-and-models-architecture.md) | Schema audit + model relationships | informed migration ordering |
| [2026-05-09-app-architecture-review.md](2026-05-09-app-architecture-review.md) | Whole-system audit before cost-aware iteration | drove the 5-phase plan in `~/.claude/plans/ok-now-we-have-distributed-anchor.md` |
| [2026-05-09-external-anthropic-financial-services.md](2026-05-09-external-anthropic-financial-services.md) | Pattern review of `anthropic/financial-services` repo | drove the free-tier follow-on plan (skills factoring, EDGAR ingest, IR YouTube) |

## When to read

- Investigating a tradeoff that was made some time ago → check the most recent review covering that area
- Planning a system-wide refactor → read the latest architecture review first to avoid re-litigating settled questions
- Considering an external pattern → check whether a review already evaluated it

## When to write a review

Reviews are one-off, not on a fixed cadence. Triggers:
- Considering a major architectural change → review the existing shape first
- External release / blog post / repo proposes a pattern that *might* fit ours → review before adopting
- Operator wants a "where are we" snapshot → review can serve as a stable reference

Naming: `YYYY-MM-DD-<short-slug>.md`.

## See also

- [`../guides/architecture.md`](../guides/architecture.md) — current architecture (always up to date)
- [`../decisions/`](../decisions/) — ADRs (binding tradeoffs)
- [`../status/roadmap-shipped.md`](../status/roadmap-shipped.md) — what shipped per review's recommendations
