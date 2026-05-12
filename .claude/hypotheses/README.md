# Hypotheses

Operator-authored hypothesis drafts. Each hypothesis is a structured
trading thesis with body, claim type, primary metric, tracking signals,
and an invalidator DSL spec. The `hypothesis` table in Postgres mirrors
this structure.

## Layout

```
hypotheses/
├── README.md            ← this file
└── draft/               ← markdown source for each hypothesis
    ├── template.md      ← structure template (copy when authoring new)
    ├── btc-bottom-3m.md
    ├── btc-rally-24m.md
    ├── latam-breakout-18m.md
    ├── latam-breakout-36m.md
    ├── saas-mission-critical-2x-18m.md
    └── stagflation-regime-24m.md
```

## When to read

- Authoring a new hypothesis → copy `draft/template.md` and fill it
- Auditing an active hypothesis surfaced by the daily tick → read `draft/<slug>.md` for the operator's articulated thesis
- Stress-testing via `/v1/research/ask` → the body becomes context in the bundle

## Schema relationship

The markdown drafts in `draft/` are the **source**. The DB row in the
`hypothesis` table is **derived** (parsed at seed time + on edit). When
the markdown and DB diverge, the markdown wins — re-seed via
`scripts/patch_invalidators.py` or the equivalent backfill route.

## See also

- [`../modules/hypotheses.md`](../modules/hypotheses.md) — module doc with table schema + invalidator DSL grammar
- [`../decisions/013-hypothesis-object.md`](../decisions/013-hypothesis-object.md) — ADR for the hypothesis object shape
- [`../plans/M-2-hypothesis-object.md`](../plans/M-2-hypothesis-object.md) — phase plan that introduced this folder
