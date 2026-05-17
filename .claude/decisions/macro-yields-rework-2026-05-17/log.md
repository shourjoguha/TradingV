# Decisions log — Macro yield-curve rework (2026-05-17)

Per-phase ship record. Format identical to ux-rework-2026-05-17/log.md.

---

## Phase 1 — Backend additions (2026-05-17)
- **Shipped**:
  - `app/macro/registry.yaml` += `WGS30YR` (FRED — 30Y treasury), `T10Y2Y` (FRED — 2s10s recession indicator), `T10Y3M` (FRED — NY Fed model input), `^MOVE` (yfinance — ICE BofA MOVE bond-vol)
  - Backend restarted; macro refresh ingested all 4 series (`POST /v1/macro/refresh` → 48 ok / 0 failed / 275k rows touched)
- **Verification**: `GET /v1/macro/series?symbol=…` returned points for each: WGS30YR=4.97, T10Y2Y=0.50, T10Y3M=0.90, ^MOVE=79.87
- **Operator-visible impact**: data layer now serves the 5 missing macro signals operator's video diet (fx-evolution-daily-w19, click-capital) repeatedly references
- **Skeptic check**: zero schema changes (registry yaml append only); no information-layer touches; one-line FRED provider invocation reused

## Phase 3 — UI surfacing (2026-05-17, merged w/ Phase 2 since MOVE landed Phase 1)
- **Shipped**:
  - `frontend/src/lib/macro-views.ts`: new `Yield curve` regime panel (6th panel) with 5 rows — 2Y / 10Y / 30Y / 2s10s / 10y-3m
  - Stress panel gains MOVE row beside VIX (VIX label updated to "VIX (equity vol)" for disambiguation)
- **Files touched**: 1 (macro-views.ts)
- **Verification**: Playwright `.audit/macro-01-with-yield-curve.png` shows 6 panels rendering correctly; click-test on 30Y Treasury row expanded inline chart (`.audit/macro-02-30y-expanded.png`)
- **Operator-visible impact**: yield-curve panel surfaces operator's video-diet signals directly; MOVE shows beside VIX in Stress
- **Skeptic check**: no new chart components; reuses existing Sparkline + RatioChart pattern; same physics/density as other panels

## Phase 4 — Glossary terms + doc updates (2026-05-17)
- **Shipped**:
  - `frontend/src/lib/glossary.ts`: 6 new entries — `yield_curve_axis`, `r_wgs2y`, `r_wgs30y`, `r_t10y2y`, `r_t10y3m`, `r_move`. Each with `short` + `long` + `directional {up,down,threshold}` per project convention.
  - `r_wgs10y` reused from Liquidity panel (no dup).
- **Files touched**: 1 (glossary.ts)
- **Verification**: TS clean (after dedup of `r_wgs10y` shadow); InfoBubble next to each row label now shows the operator-tuned threshold guidance ("30Y >5% sustained = fear-of-unknown")
- **Operator-visible impact**: hover-tooltips on every yield-curve row explain what each rate means and what threshold to watch

## Phase 5 — E2E verification + decisions log retro (2026-05-17)
- **Verification matrix**:
  - Backend tests: 21 macro tests pass (`pytest -k macro`) — no regressions
  - TS check: clean
  - Playwright walk: /macro renders 6 panels at 1440 desktop; each new row's sparkline populates from latest refresh; clicking any row expands a 5-year focused chart with correct data; new InfoBubbles work
  - FRED series queryable end-to-end via the existing /v1/macro/series endpoint
  - yfinance ^MOVE series queryable end-to-end
- **Decisions log**: this file + `00-audit-and-plan.md` capture full council reasoning
- **Roadmap entry**: appended to `.claude/status/roadmap-shipped.md`
- **Skeptic check**: did NOT add multi-line yield-curve chart (3 rates on one axis); did NOT add BTC to macro (operator-deferred); did NOT touch information layer
- **Out-of-scope deferred**:
  - Multi-line yield-curve chart (would need new chart component; defer unless operator asks)
  - Smart-money options-flow (per-ticker concern, not macro)
  - Tom Lee 7300 / specific price targets (narrative, not macro)

---
