# Macro yield-curve gap audit + phased plan (2026-05-17)

## Trigger

Operator: "missing context on the macro view. fx-evolution-daily + click-capital folders repeatedly reference US bond yield curves across mid-long horizon (2/3/10/30 year + ratios) — important for larger context."

## Audit — what's referenced repeatedly in `Videos/{click-capital, fx-evolution-daily}`

Grep counts of concept mentions across both folders' transcripts:

| Concept | files | citation excerpts |
|---|---|---|
| **US Treasury 10y** | 4 | fx-evolution-2026-05-06 "10year getting close to 4.5"; fx-evolution-2026-05-08 "2year"; click-capital-2026-05-09 "TLT, longdated Treasury bonds"; fx-evolution-w19 explicit "US 10 year is about to potentially break up" |
| **US Treasury 30y** | 2 | fx-evolution-2026-05-10 "US30y. If that breaks"; fx-evolution-w19 "US 30 year is playing very closely with that all important 5%" |
| **Yield curve / 2s10s** | 2 | click-capital-2026-05-09 "inverted yield curve"; click-capital-2026-04-25 "yield curve still very much" |
| **MOVE index (bond vol)** | 1 explicit | fx-evolution-w19 "MOVE … bond market option volatility … first sign bonds market actually cares" |
| **DXY / dollar index** | 4+ | fx-evolution-w19 "dollar trapped between 97.5 and 99"; explicit chart references |
| **VIX** | 4 files | click-capital-2026-04-17, 2026-04-08, 2026-05-02, fx-evolution-2026-05-08 |
| **Copper** | 4+ | click-capital-2026-05-09 "copper wires, uranium"; fx-evolution-2026-05-13 "copper was on the move" |
| **Gold** | 13 files | fx-evolution-w19 "gold $4500 psychological"; click-capital "gold during January" |
| **HYG / credit spreads** | 3 | fx-evolution-w19 "meta five year credit default swaps on the rise" |
| **Tom Lee 7300** | 1 | fx-evolution-w19 (operator-tracked target, not macro signal — out of scope) |

## Gap analysis vs existing macro view

Macro Workbench currently has 5 panels (Inflation / Growth / Liquidity / Stress / Inflation regime) + 9-sector strip. The existing registry (`app/macro/registry.yaml`) covers most of the audit signals — but with three explicit gaps:

| Signal | Existing? | Gap |
|---|---|---|
| 10Y treasury (WGS10YR) | ✓ in Liquidity panel | — |
| 2Y treasury (WGS2YR) | ✓ in registry but NOT in any UI panel | UI surfacing |
| 30Y treasury | ✗ NOT in registry | **add WGS30YR (FRED)** |
| 2s10s spread (T10Y2Y) | ✗ NOT in registry | **add T10Y2Y (FRED)** — recession leading indicator |
| 10Y-3M spread (T10Y3M) | ✗ NOT in registry | **add T10Y3M (FRED)** — NY Fed recession model |
| MOVE index (bond vol) | ✗ NOT in registry | **add ^MOVE (yfinance, may not exist)** OR document gap |
| Dedicated "Yield curve" panel | ✗ | **add 6th REGIME_PANEL** |
| HYG / IG credit | ✓ in Stress panel | — |
| DXY | ✓ in Stress panel | — |
| VIX | ✓ in Stress panel | — |
| Copper/Gold/Oil ratios | ✓ in Inflation panel | — |
| Bitcoin (BTC-USD) | ✓ in registry, NOT in UI | already deferred (operator decision) |

## Council deliberation (synthesized — no need for parallel agents, gap is well-scoped)

**UX strategist**: Add "Yield curve" as a 6th regime panel below "Inflation regime". Operator's mental model from the videos is yields-driven; deserves its own panel. Each row is a single-series chart (no ratio) — same Sparkline + RatioChart pattern as Liquidity panel.

**Visual designer**: Yield curve panel should show 3 rates (2y/10y/30y) as same-axis lines for true curve shape, but that needs a multi-line chart component. Phase 1 ship is 3 single-line series rows + 2 spread rows (which are essentially curve shape via difference) — operator gets the data; multi-line chart deferred to Phase N if asked.

**Frontend architect**: macro-views.ts pattern handles this with zero new code — REGIME_PANELS array, just append a new panel entry. Backend registry.yaml adds 3 FRED series (additive, no schema change). One new term entry in glossary for `r_yield_curve_panel`.

**Skeptic**:
- Don't add new chart components. Use existing Sparkline + RatioChart.
- Don't go down the MOVE-index rabbit hole if yfinance doesn't have it — fall back to documenting gap; equity-vol VIX still surfaces "stress".
- Skip BTC surfacing on macro (it's in registry but operator deferred — keep deferred).
- Don't reshape Macro page IA; just add a panel.

## Phased plan

### Phase 1 — Backend additions
Append to `app/macro/registry.yaml`:
- `WGS30YR` (FRED — 30Y treasury constant maturity)
- `T10Y2Y` (FRED — 10y minus 2y spread; recession indicator)
- `T10Y3M` (FRED — 10y minus 3-month spread; NY Fed recession model input)

Verify FRED provider returns data for each. Run macro refresh to backfill.

### Phase 2 — MOVE index probe
Test if yfinance returns `^MOVE` (ICE BofA MOVE Index). If yes, register; if no, register `TLT` as already covered + document gap.

### Phase 3 — UI surfacing
Append "Yield curve" panel to `frontend/src/lib/macro-views.ts`:
- 2Y treasury (single series)
- 10Y treasury (single series — already in Liquidity, keep there too OR move)
- 30Y treasury (single series)
- 2s10s spread (FRED series T10Y2Y — single series)
- 10y-3m spread (T10Y3M — single series)

If MOVE landed, add to Stress panel below VIX.

### Phase 4 — Glossary terms + doc updates
- Add `r_wgs30y`, `r_t10y2y`, `r_t10y3m`, `r_yield_curve_panel`, `r_move_index` to glossary.
- Update `.claude/modules/macro.md` (if exists) or `.claude/decisions/macro-yields-rework-2026-05-17/log.md` per-phase.

### Phase 5 — Verification + decisions log retro
Playwright walk of /macro showing the new panel; backend test for the new symbols (refresh + series endpoints return data); operator-visible delta documented.

## Out of scope

- Multi-line yield-curve chart (3 rates on one axis) — defer until operator asks.
- BTC on macro view — operator deferred.
- Tom Lee 7300 / specific price targets — narrative, not macro signal.
- Smart-money options-flow surfaces (Dark Pool, RSI levels) — operator's individual ticker work, not macro context.

## Decision log file

Per-phase ship + verification + skeptic-check + gaps at `log.md` (same dir).
