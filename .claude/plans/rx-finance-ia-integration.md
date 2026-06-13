# Plan — rx-finance IA integration

Right now `/rx-finance` lives as an orphan top-level route with no sidebar nav. Need to fold it into the existing IA without bloating it.

## Existing IA (sidebar, 5 groups)

| Group | Role | Children |
|---|---|---|
| Today | morning glance (passive scan) | DriftCard, FreshSignals, ResearchCurious, MarketMood + strips |
| Decide | numerical/market-state (proactive scan) | Signals (Motion), Predictions, Macro, Watchlist |
| Think | narrative/intelligence | Research, Theses, TV Context, The Street |
| Admin | system config | Admin, Legacy Dashboard |
| Docs | reference | — |

## Where rx-finance belongs

rx-finance has three sub-surfaces of different character:

| Sub-surface | Operator job | Closest existing kin |
|---|---|---|
| **Rec list** (`/rx-finance`) | "what do I need to decide?" | Motion (Opportunities = should I act?) |
| **Rec detail** (`/rx-finance/:id`) | "decide this one rec" | Motion (Trades = what I did about it) |
| **Positions** (`/rx-finance/positions`) | "what am I currently exposed to?" | Motion (aggregates Trades) |
| **Hypothesis health** (`/rx-finance/hypotheses`) | "are my theses still valid?" | Think → Theses (thesis hygiene) |
| **Open-rec awareness on morning glance** | "anything pending overnight?" | Today (strip pattern) |

Council voices:
- **Architect**: don't introduce a 6th top-level group for a layer that's a *projection* over Motion + Theses data. Fold into existing groups along their natural job boundary.
- **Pragmatist**: the rec LIST is a single-tab page; promoting it to a top-level needs ≥3 sibling tabs to justify the sidebar real estate. It has 1 (just the list). Tab inside Motion instead.
- **Critic**: don't scatter four routes across three groups — the operator still needs ONE place to see all open recs. Solution: rec list is the Motion default; everything else is detail/aux.
- **Skeptic**: Today is already crowded (2x2 + 3 strips + pending panel). Adding another strip risks card-fatigue. Mitigate: cap to 3 rows + only show when there are aging/forced recs.

## Decision — slot rx into Motion + Theses, surface awareness on Today

1. **Motion gains 2 tabs**: `Opportunities | Trades | Positions | Recs`
   - `/motion/recs` → RxFinance list (default route stays Opportunities)
   - `/motion/recs/:id` → RxFinanceDetail
   - `/motion/positions` → RxFinancePositions
2. **Theses gains 1 tab**: `List | Health`
   - `/theses` → existing Theses (default)
   - `/theses/health` → RxFinanceHypotheses
3. **Today gains 1 strip**: `RxStrip` between `TickerReviewStrip` and `TVContextStrip`
   - Shows top 3 open finance recs sorted by aging-first then drift_score
   - Per-row: short_id · tldr_short · drift bar · status · age chip · "Decide" → `/motion/recs/{id}`
   - Hidden when no open recs (operator-respectful empty-state pattern)
4. **Old `/rx-finance*` routes → redirect** to new paths for any bookmarks operator might have made in the last hour
5. **Sidebar update**: no new entries. Motion subnav already at `/motion` covers the new tabs (Motion is currently labeled "Signals" in the sidebar — keep that label since the operator-recognized word for the group is still signals/opportunities/trades, not "Motion").

## Files to edit

### Frontend

| File | Change |
|---|---|
| `pages/Motion.tsx` | Add `positions` + `recs` to TABS. Map them to `RxFinancePositions` + `RxFinance` components. Detail route handled below. |
| `pages/Theses.tsx` | Wrap in a tab shell; existing list becomes the `list` tab; new `health` tab renders `RxFinanceHypotheses`. (Or: extract tab wrapper to keep diff smaller and have Theses opt in.) |
| `pages/RxFinance.tsx` | Remove subnav chips (Hypotheses/Positions) — now top-level tabs in Motion + Theses. Adjust internal navigate target from `/rx-finance/{id}` → `/motion/recs/{id}`. |
| `pages/RxFinanceDetail.tsx` | Adjust back-link from `/rx-finance` → `/motion/recs`. Update any internal anchor refs. |
| `pages/RxFinanceHypotheses.tsx` | Drop the `← Recs` link (now a tab on Theses). |
| `pages/RxFinancePositions.tsx` | Drop the `← Recs` link (now a tab on Motion). |
| `pages/Today.tsx` | Insert `<RxStrip />` between TickerReviewStrip + TVContextStrip. |
| `components/Today/RxStrip.tsx` (NEW) | Top-3 open recs, hidden when empty. Mirror `TickerReviewStrip` aesthetic. |
| `App.tsx` | Replace top-level `/rx-finance*` routes with redirects. Add `/motion/recs` + `/motion/recs/:id` + `/motion/positions` (handled by Motion's tab shell + new param route for detail). Theses route updates for tab shell. |

### Backend

None. All endpoints already exist (`/v1/rx/recs*`, `/v1/hypotheses/health/list`, `/v1/trades/positions`).

### Docs

- `.claude/modules/rx.md` — update Frontend section
- `.claude/frontend/pages.md` — add new routes
- `.claude/status/roadmap-shipped.md` — log IA integration retro

## Verification

1. Sidebar: no new entries; Motion subnav (via Decide group) unchanged
2. `/motion` default = Opportunities (unchanged)
3. `/motion/recs` = rec list (was `/rx-finance`)
4. `/motion/recs/<uuid>` = rec detail (was `/rx-finance/<uuid>`)
5. `/motion/positions` = positions (was `/rx-finance/positions`)
6. `/theses` default = list (unchanged)
7. `/theses/health` = hypothesis health
8. Bookmarked `/rx-finance*` URLs all redirect properly
9. Today renders RxStrip when open recs exist; hidden when none
10. Detail-page cross-ref cards still link correctly (hypotheses → wherever, trades → wherever)
11. Trade form rec autocomplete still works (no change)

## Skip in this cut

- Custom subnav INSIDE the rec detail (cross-refs already inline)
- A dedicated rx-finance landing page outside Motion (one path per operator action — Motion IS the action surface)
- Sidebar badge counts (e.g. "Motion (3 open recs)") — defer until operator asks; risks notification overload
- Sound/badge for forced-decision recs — same
