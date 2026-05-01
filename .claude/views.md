# Views

Markdown-with-frontmatter view registry. Lets the operator group ratios,
series, and hypothesis filters into named workbench layouts without a DB
table — files in version control are the source of truth.

Phase: M-2 (shipped 2026-05-01).

## Why files, not a table

- Editing a view = editing a file in your editor of choice. No CRUD UI to
  build, no migrations when fields change.
- Diffable in git. Every operator change is captured.
- Frontend reads `/v1/views` — backend is just a parser.

## Frontmatter shape

```yaml
---
id: macro_liquidity                # UNIQUE within registry; alphanum + _ -
title: "Liquidity & Credit"
default_axis: liquidity            # optional — pre-selects an axis filter
panels:
  - kind: ratio                    # 'ratio' | 'series' | 'spread' | 'hypothesis_filter'
    numerator: "WALCL"
    denominator: "GDP"
    sma_days: 200
  - kind: series
    symbol: "DGS10"
    threshold: 4.5
  - kind: hypothesis_filter
    axis: liquidity
---

# Markdown body — operator notes about this view.
```

Files live at [`app/views/registry/*.md`](../app/views/registry/). Two
seeded out of the box: `macro_liquidity`, `macro_growth_inflation`. Add
more by dropping `.md` files in the dir; reload via process restart or
`/v1/views/_reload` (not yet implemented — restart for now).

## Parser behaviour

- Splits on `---` markers; `yaml.safe_load` on the front block.
- `id` defaults to filename stem if omitted.
- Pydantic-validates against `ViewSpec` ([parser.py](../app/views/parser.py)).
- **Boot fails loudly on parse error** — operator sees the broken file
  immediately, not a silent half-loaded registry. Tests cover this path.

## Routes

```
GET /v1/views          {items: [ViewSpec, ...], count}
GET /v1/views/{id}     ViewSpec
```

API-key-gated. Reads from the in-memory `parser.REGISTRY` populated at
startup by `parser.reload()` (called from `app/main.py` lifespan).

## Frontend

`useViews()` in [use-api.ts](../frontend/src/hooks/use-api.ts) and
`ViewSpec` / `ViewPanel` types in
[lib/types.ts](../frontend/src/lib/types.ts). No dedicated frontend page
yet — views are consumed elsewhere (planned: macro page can render a view
spec directly when M-2 surface needs it).

## Add a view

1. Drop `app/views/registry/<id>.md` with frontmatter as above.
2. Restart the API process.
3. `GET /v1/views` returns the new entry.

Adding new panel kinds requires extending `PanelSpec` in
[parser.py](../app/views/parser.py) — fields are intentionally loose
(all `Optional`) so additive changes don't break existing files.
