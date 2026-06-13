# Handover — Chart-modularity audit (2026-05-17)

## Why this doc exists

After shipping 3 rounds of Macro Sectors viz (RS Leadership Ladder → compact grid + Cycle Phase Wheel + always-on chart → dropdown selector w/ 4 viz), the operator asked for a full audit of every chart-contributing file across the app: are they modular, or hardcoded and scattered? This doc captures the audit's findings, the refactor wins it recommended, **the assumptions baked into those recommendations**, and a stress-test checklist for the next session to verify the first-pass didn't miss anything material.

## What was audited (scope)

- Every file under `frontend/src/components/macro/`
- Every file referencing `lightweight-charts` (currently 2 callsites: `components/macro/RatioChart.tsx` and `pages/PredictionsByTarget.tsx`)
- Every file with inline `<svg`, `<canvas`, or computed-style charts
- Reusable primitives in `components/common/` (specifically `DriftBar.tsx`)
- Inline "chart-shaped" components in `components/today/*` (DriftCard, FreshSignalsCard, MarketMoodCard, RxStrip, etc.)
- `components/the-street/*` (TierTable, the deleted TickerTimeline/SnapshotPicker not in audit)
- `components/rx/*` for any chart-like surfaces

## Method

The audit was performed by an Explore subagent w/ tool access (`Read`, `Glob`, `Grep`, `Bash` for `wc -l` and hex-literal counts). It produced:
1. Chart inventory table (file · type · LOC · reuse count)
2. Reusable vs one-off classification
3. Library-choice survey (lightweight-charts vs custom SVG vs CSS)
4. Hex-literal density top-5 ranking
5. 4/10 modularity verdict w/ 2-sentence rationale
6. Top 3 refactor wins ranked by payoff:effort

## Headline findings

| Score | 4/10 |
|---|---|
| Reusable primitives | 3 — `Sparkline.tsx` (5 callsites) · `RatioChart.tsx` (3 callsites) · `DriftBar.tsx` (3 callsites) — all well-factored, clean props |
| One-off "chart-shaped" components | 5 — `CyclePhaseWheel` · `CorrelationHeatmap` · `RotationFootprintStrip` · `RegimeConditionalBadges` · `SectorLadderCard` (single-use, geometry/colors hardcoded) |
| Worst offender | `pages/PredictionsByTarget.tsx` — 350 LOC w/ inline lightweight-charts setup + 24 hex literals + 10-color `PREDICTION_COLORS` array all in one page |

**Source-of-truth violations identified**:
- Lightweight-charts theme defined twice (`RatioChart.tsx` exports `PALETTE`; `PredictionsByTarget.tsx` hardcodes inline). Same library, two drift-prone themes.
- Identity colors live in BOTH `tailwind.config.js` (CSS classes) AND `lib/macro-views.ts` (`SECTOR_IDENTITY_HEX` for SVG fill). Hand-synced, breakable.

**Hex-literal density top 5** (highest = most hardcoded):
1. `PredictionsByTarget.tsx` — 24
2. `CyclePhaseWheel.tsx` — 12
3. `CorrelationHeatmap.tsx` — 9
4. `RatioChart.tsx` — 5 (mitigated: exported `PALETTE` const)
5. `Sparkline.tsx` — 3

## Top 3 refactor wins (audit's ranking)

| # | Win | Effort | Payoff | What |
|---|---|---|---|---|
| 1 | Extract `PredictionsByTarget` chart-theme to factory | ~1h | 10/10 | New `lib/chart-themes.ts` w/ `createPredictionChartConfig()` + `PREDICTION_COLORS` named const. Wire into `PredictionsByTarget.tsx` + `RatioChart.tsx`. Single source of truth for lightweight-charts theming. |
| 2 | Correlation-heatmap → reusable primitive | ~2h | 8/10 | Extract `corrColor()` + `corrFg()` to `<HeatmapCell>`; wrap in `<CorrelationTable>` w/ `values` + `lookback` props. |
| 3 | SVG geometry → lib | ~3h | 6/10 | Extract `donutSectorPath` / `polar` / `dotRadius` from `CyclePhaseWheel` to `lib/svg-geometry.ts`. Parameterize SIZE/OUTER_R/INNER_R. Unblocks future arc-segment viz + makes math unit-testable. |

## Skeptic-cleared "don't refactor" list

The audit explicitly declined to refactor:
- `RotationFootprintStrip`, `RegimeConditionalBadges`, `SectorLadderCard` — single-use bespoke is fine. No second-use site demands extraction. Refactoring before demand = speculative architecture.
- `Sparkline`, `DriftBar`, `RatioChart` — already modular. Leave alone.

---

## ⚠ STRESS TEST — verify before acting on findings

This audit was a single Explore-agent pass. Before treating the verdict as ground truth or shipping win #1, the next session should stress-test for the failure modes below. **None of these were checked in the original audit.**

### 1. Coverage blindspots — did the audit miss any chart-rendering surface?

The audit's `grep` net was: `lightweight-charts`, `<svg`, `<canvas`, `createChart`, `tabular-nums.*Sparkline`. **Possibly missed**:
- Chart-like surfaces built w/ pure CSS gradients / `linear-gradient` backgrounds (search: `linear-gradient`, `radial-gradient`, `conic-gradient`)
- Inline progress / scalar bars not named `*Bar.tsx` (search: `width:.*%`, `style={{ width:` for dynamic widths)
- ASCII-art-style "charts" using box-drawing chars or `▮▯▰▱` (rare but possible in compact heatmaps)
- Components that import from external chart libs other than `lightweight-charts` (search: `from 'recharts'`, `from 'd3'`, `from 'visx'`, `from 'chart.js'` — even if package.json doesn't list them, code may have stale imports)
- `<img>` tags with chart screenshots embedded (shouldn't exist but verify)

**Verification command**:
```bash
cd frontend && rg -l '<svg|<canvas|createChart|linear-gradient|radial-gradient|conic-gradient|from .recharts.|from .d3.|from .visx.|from .chart.js.' src
```
Compare result count to audit's inventory; any new files → audit missed them.

### 2. "Reusable" claim — verify Sparkline / DriftBar / RatioChart are actually as clean as the audit claims

The audit said these have "clean props, no hardcoded data." Stress-test:
- For each: read the component, list the props. Are any props OPTIONAL with hardcoded defaults that callers rely on (silent coupling)?
- Are there any `useEffect` blocks fetching data inside the component? (would break the "no hardcoded data" claim)
- Are there any inline `if (props.symbol === 'XLE')`-style branches embedded? (would prove they're NOT generic primitives)

**Verification commands**:
```bash
cd frontend && for f in src/components/macro/Sparkline.tsx src/components/macro/RatioChart.tsx src/components/common/DriftBar.tsx; do
  echo "=== $f ==="
  grep -nE 'useEffect|useQuery|=== .XL|=== .SPY|fetch\(|apiFetch' "$f"
done
```
Any hit on `useEffect`/`useQuery`/`apiFetch` or symbol-literal branches → primitive isn't as pure as claimed.

### 3. Effort estimate — is win #1 really ~1h?

The audit estimated **1h** for the chart-theme factory extraction. Stress-test the assumption:
- How many places consume the `PredictionsByTarget` chart? (audit said "1 page-only" — verify by `grep -r 'PredictionsByTarget' src`)
- Does `RatioChart`'s `PALETTE` export cover everything `PredictionsByTarget` hardcodes, or are there fields only one has?
- Are there theme-dependent values inside lightweight-charts options that DON'T map cleanly to either palette (e.g. `crosshair.mode`, `timeScale.timeVisible` — non-color config that lives next to color in `createChart()`)? If yes, factory needs broader scope.
- Tests: does `PredictionsByTarget` have any snapshot tests or E2E that lock the current rendering? Refactor risk if yes.

**Verification commands**:
```bash
cd frontend && grep -rn 'PredictionsByTarget' src
cd frontend && grep -nE 'createChart|addCandlestickSeries|addLineSeries' src/pages/PredictionsByTarget.tsx | wc -l
cd frontend && grep -nE 'PREDICTION_COLORS' src
ls .audit/*predictions*.png 2>/dev/null  # any visual baselines?
```

### 4. Hidden coupling — does Sparkline depend on caller-specific data shape?

`Sparkline` accepts `points: MacroPoint[]` per its prop type. But:
- Does it gracefully handle empty/single-point/all-zero data? (`Sparkline.tsx:60` — `if (data.length < 2) return { ... lineColor: '#94A3B8' }` — yes, but lineColor falls back to grey w/o using props' tone hint)
- Z-scored series (Sector ladder use case) has values centered on 0; does the delta-pct calc make sense for centered series? (`Sparkline.tsx:75` computes `delta = ((last - first) / first) * 100` — for z-scores `first` is often 0, divide-by-zero risk; verify)

**Verification command**:
```bash
cd frontend && cat src/components/macro/Sparkline.tsx | grep -A 2 'delta = '
```
If divide-by-zero isn't guarded for centered/zero-starting series, ladder rendering is fragile.

### 5. "Don't refactor" list — are the skeptic-cleared declines actually safe?

The audit declined `RotationFootprintStrip`, `RegimeConditionalBadges`, `SectorLadderCard` for "single-use bespoke is fine." Stress-test:
- For each, has the operator hinted at a 2nd use site? (search `.claude/plans/*.md` for forward-looking references)
- Will the dropdown selector likely accept new viz options? If yes, the precedent already exists — extracting a `<SectorVizCard>` wrapper might be cheap.
- If the operator iterates on the wheel a 4th time (likely, given pattern), the bespoke-OK call ages badly.

**Verification command**:
```bash
grep -rn 'RotationFootprint\|RegimeConditional\|SectorLadder\|CyclePhaseWheel\|second wheel\|reuse' /Users/shourjosmac/.claude/plans/ 2>/dev/null
```

### 6. Library-choice gaps — are there charts that *should* use lightweight-charts but use SVG, or vice versa?

The audit listed which uses which but didn't ask "is the choice right?":
- `CorrelationHeatmap` is an HTML `<table>` w/ inline styles. Would benefit from `lightweight-charts`? No — heatmaps aren't a chart-lib strength. Probably correct.
- `RotationFootprintStrip` is a CSS grid. Same call — no chart lib needed.
- `CyclePhaseWheel` is pure SVG. Could `lightweight-charts` do donut sectors? No — it's a time-series lib. SVG is correct.
- But is there a small chart that's using lightweight-charts when a Sparkline would do? (search for `createChart` outside `RatioChart` + `PredictionsByTarget`)

**Verification command**:
```bash
cd frontend && grep -rn 'createChart\|lightweight-charts' src/components/ src/pages/
```
Any 3rd `createChart` callsite = potential over-engineering or undocumented chart.

### 7. Test coverage — what will break if win #1 ships?

The audit didn't check tests. Stress-test:
```bash
cd frontend && find src -name '*.test.tsx' -o -name '*.spec.tsx' 2>/dev/null
# Look for any *predictions* or *chart* test
grep -rl 'PredictionsByTarget\|createPredictionChart\|PREDICTION_COLORS' frontend 2>/dev/null
ls .audit/*.png | head -20  # visual regression baselines?
```
If there's a Playwright e2e on `/predictions/target`, the refactor needs a pre/post screenshot diff.

---

## Pending decision

**Operator was last asked**: "want me to proceed w/ win #1?" — no answer yet at compact time.

If operator says yes, the recommended sequence:
1. Run the **stress-test commands above** first (10 min) — confirm 1h estimate, confirm no missed surfaces
2. Create `lib/chart-themes.ts` with `createPredictionChartConfig()` + `createMacroRatioChartConfig()` + `PREDICTION_COLORS` const
3. Pull color literals from existing Tailwind tokens (`success`/`danger`/`identity-*`) via a `getCssVar()` helper or by extending `tailwind.config.js` w/ a `chart` palette block
4. Wire `PredictionsByTarget.tsx` to the factory; remove inline hex literals
5. Wire `RatioChart.tsx` to the factory; remove the local `PALETTE` const
6. Playwright before/after on `/predictions/target` + `/macro` + `/macro/sectors` (RatioChart drill-in) — verify zero visual regression
7. Append retro entry to `.claude/status/roadmap-shipped.md`

If operator declines or defers, leave the audit findings in this doc + `.claude/status/roadmap-shipped.md` retro for future reference.

## Critical files (for next session)

- **Audit subject** (don't modify in refactor #1): `frontend/src/pages/PredictionsByTarget.tsx`, `frontend/src/components/macro/RatioChart.tsx`
- **Audit target** (will be created in refactor #1): `frontend/src/lib/chart-themes.ts`
- **Source of truth** for design tokens: `frontend/tailwind.config.js` (especially `colors.success`, `colors.danger`, `colors.identity.*`)
- **Identity-color sync hazard**: `frontend/src/lib/macro-views.ts` (`SECTOR_IDENTITY_BG` + `SECTOR_IDENTITY_HEX`) — any change to identity palette must update BOTH
- **Macro module doc** (already updated this session): `.claude/modules/macro.md` — has full Sectors architecture + math contracts
- **Roadmap retros** (already updated this session): `.claude/status/roadmap-shipped.md` — top 4 entries cover the chart audit, the 3-round Sectors rebuild, and the density audits that preceded it
- **Plan file**: `~/.claude/plans/now-when-i-use-radiant-yao.md` — original brainstorm + deferred items realized

## How to read the audit's verdict skeptically

The 4/10 modularity score is one Explore agent's call. The score itself is less important than the **directional finding**: the codebase has good primitives but loose composition. If the stress test reveals the audit overestimated reusability (e.g. Sparkline has hidden coupling) or underestimated it (e.g. found a 4th use site for one of the "one-off" components), the score and the refactor priorities should both shift.

Treat this handover as a **starting hypothesis**, not a finished diagnosis.
