# M-1f — Macro Workbench frontend (signal layer UI)

> **Status:** ✅ SHIPPED 2026-04-30. See [macro.md § Frontend](../macro.md#frontend-macro-lazy-loaded) for the as-built doc.
> **Backend dependency:** M-1 ([macro.md](../macro.md)) shipped 2026-04-30 — `/v1/macro/{series,ratio,refresh}` live.
> **Source-of-truth design:** [macro-workbench-brainstorm.md](../macro-workbench-brainstorm.md).
> **UX skill consulted:** `~/.claude/skills/ui-ux-pro-max` (Data-Dense + Heatmap patterns; line + sparkline + grouped-bar recommendations) + `frontend-design`.

## Operator decisions (locked)

- Default time window: **5y**.
- Sparklines: **weekly close** resolution; focused charts: **daily**.
- Row interaction: **inline expand** (no nav round-trip).
- Theme: **neumorphic light** preserved. No dark mode, no glassmorphism.
- Charting: **lightweight-charts ^4.2.1** (already in `package.json`). No new deps.

## Information architecture

Single `/macro` route with three sub-tabs (segmented control), lazy-loaded:

| Sub-tab | Default | Purpose |
|---|---|---|
| Overview | yes | 4 regime-axis panels (Inflation / Growth / Liquidity / Stress) × 3 ratio rows each — 12 sparklines on one screen |
| Ratios | — | One full-size focused chart with quick-switch dropdown |
| Sectors | — | 9-cell sector-vs-SPY strip with cell color = current Δ% vs window-start |

URL pattern: `/macro/:tab?` so deep-linking works (`/macro/sectors`).

## Files

| File | Purpose |
|---|---|
| `frontend/src/pages/Macro.tsx` | Page shell + sub-tabs + refresh button |
| `frontend/src/components/macro/RegimePanel.tsx` | Neumorphic card containing 3 sparkline rows |
| `frontend/src/components/macro/Sparkline.tsx` | Hand-rolled SVG sparkline; weekly resolution |
| `frontend/src/components/macro/RatioChart.tsx` | lightweight-charts line wrapper, neumorphic-themed |
| `frontend/src/components/macro/SectorStrip.tsx` | 9-cell sector ratio strip |
| `frontend/src/lib/macro-views.ts` | Single source of truth: which ratios live in which panel + their display metadata |
| `frontend/src/hooks/use-api.ts` | Add `useMacroSeries`, `useMacroRatio`, `useMacroRefresh` |
| `frontend/src/lib/types.ts` | `MacroPoint`, `MacroSeriesResponse`, `MacroRatioResponse`, `MacroRefreshResponse` |
| `frontend/src/App.tsx` | Lazy route `/macro/:tab?` |
| `frontend/src/components/Layout.tsx` | Sidebar entry between Trades and Docs |

## Macro views config (locked)

12 ratios + standalone macro series, four axes:

```ts
// frontend/src/lib/macro-views.ts
export const REGIME_PANELS = [
  {
    title: 'Inflation',
    rows: [
      { id: 'gold/spy',     numerator: 'GC=F', denominator: 'SPY' },
      { id: 'copper/gold',  numerator: 'HG=F', denominator: 'GC=F' },
      { id: 'oil/gold',     numerator: 'CL=F', denominator: 'GC=F' },
    ],
  },
  {
    title: 'Growth',
    rows: [
      { id: 'rsp/spy',      numerator: 'RSP', denominator: 'SPY' },
      { id: 'iwm/spy',      numerator: 'IWM', denominator: 'SPY' },
      { id: 'eem/spy',      numerator: 'EEM', denominator: 'SPY' },
    ],
  },
  {
    title: 'Liquidity',
    rows: [
      { id: 'walcl',        symbol: 'WALCL', source: 'fred' },
      { id: 't10yie',       symbol: 'T10YIE', source: 'fred' },
      { id: '10y-2y-spread', /* computed in hook */ },
    ],
  },
  {
    title: 'Stress',
    rows: [
      { id: 'hyg/lqd',      numerator: 'HYG', denominator: 'LQD' },
      { id: 'tlt/spy',      numerator: 'TLT', denominator: 'SPY' },
      { id: 'dxy',          symbol: 'DX-Y.NYB' },
    ],
  },
];

export const SECTOR_ETFS = ['XLK','XLF','XLE','XLV','XLI','XLP','XLY','XLU','XLB'];
```

Editing this config = adding/swapping a row in the UI. No code changes elsewhere.

## Defer to M-2 (do NOT build now)

- Hypothesis-aware tagging of ratios ("this ratio is referenced by hypothesis X").
- Composite "regime label" (risk-on/off single number).
- Annotation overlays for events.

## Verification

- TS check clean.
- `/macro` renders all 4 panels with sparklines using cached data.
- Click row → inline expand shows full chart with time-range chips.
- `/macro/sectors` → 9-cell strip colors correctly.
- Refresh button → POST works, toast confirms `ok` count.
- Sidebar navigation works on mobile (hamburger).
