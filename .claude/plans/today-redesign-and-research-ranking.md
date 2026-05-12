# Today landing redesign + research-queue ranking

## Context

Operator's morning glance is overwhelmed by 10+ pending research approvals stacked vertically with inline Approve/Dismiss buttons. Current behaviour: operator blanket-dismisses to clear the noise, losing the signal the auto-stress was meant to surface.

Cause is not just layout — it's volume × placement × ranking:
- **Volume:** auto-stress + manual `/research/ask` accumulate uncapped.
- **Placement:** approval is focused-work, but lives on a glance-page.
- **Ranking:** queries surface in chronological order, so age dominates over quality. Oldest noise hides the most-recently-relevant signal.

Demo's `Today` page uses a 2×2 narrative grid where each card previews data with no inline actions — actions live one click away on a dedicated page. We adopt that discipline on main and add server-side ranking + auto-aging behind it.

## Approach (operator-locked)

1. **2×2 symmetric narrative grid** at the top of `/`. Four cards: drift, fresh signals, research-curious, market mood. Each carries a role description that survives empty state.
2. **No inline action buttons** on the Today page. Approval moves to `/research`.
3. **Bottom-of-page "Pending review" panel** — compressed, top-5 only, ranked by composite score (not age), inline expand (no modal hop), footer link to full queue.
4. **Server-side score column** on `research_queries`. Rank = `1.0·has_action + 0.8·at_risk_hyp + 0.6·recent_at_risk_eval + 0.4·log1p(cost_usd) − 0.5·dismiss_rate − 0.05·age_days`. Composite recomputed nightly + on status change.
5. **Auto-defer + 30-day age-out.** Queries outside top-5 get `is_deferred=true`. Queries idle >30 days get auto-dismissed with reason `auto-aged-out`. The score's recency penalty means a deferred query can climb back to top-5 if its hypothesis becomes at-risk later.

## Phases

### Phase 1 — Backend: score column + auto-age sweep (~6h)

**Deliverables:**

1. Migration `0027_research_query_scoring.py`:
   - `research_queries.score FLOAT NULL` (NULL = not yet computed)
   - `research_queries.is_deferred BOOLEAN NOT NULL DEFAULT FALSE`
   - `research_queries.auto_aged_at TIMESTAMPTZ NULL`
   - Index on `(status, is_deferred, score DESC)` for the top-5 query
2. `app/research/ranking.py` new module:
   - `compute_score(query, hypothesis, recent_eval, dismiss_rate, now) -> float`
   - `recompute_all_pending(session)` — bulk recompute, called from retention loop
   - `auto_age_expired(session, threshold_days=30)` — flip stale pending to `dismissed` with `approved_action={"reason": "auto-aged-out"}`
3. `GET /v1/research/queries` extended:
   - New param `?order=score|asked_at` (default `asked_at` for backwards compat; landing uses `score`)
   - New param `?include_deferred=false` (default true for backwards compat; landing uses false)
   - When `order=score`, sort by `score DESC NULLS LAST, asked_at DESC`
4. Score updated on:
   - Query creation (initial score, hypothesis lookup)
   - Query status change (irrelevant since approved/dismissed don't show, but cleared for sanity)
   - Hypothesis evaluation change (delta from recent_eval signal)
   - Nightly via retention loop
5. Retention loop gains `_sweep_research_queries_age` step that calls `auto_age_expired(30)` after the existing status-based sweep.
6. Tests:
   - `test_score_at_risk_hypothesis_outranks_normal` (at_risk gets boost)
   - `test_score_with_proposed_action_outranks_verdict_only`
   - `test_score_recent_query_outranks_old`
   - `test_dismissal_rate_penalty` (operator-historic dismiss-rate lowers score)
   - `test_auto_age_dismisses_30day_pending`
   - `test_top5_endpoint_returns_ordered_by_score`

**Reuses:**
- `app/research/models.py` ResearchQuery (extend, don't rewrite)
- `app/hypotheses/service.py` for hypothesis at-risk + recent-eval lookups
- `app/admin/retention.py` for sweep integration

### Phase 2 — Frontend: 2×2 grid + pending review panel (~6h)

**Deliverables:**

1. Four narrative cards (`frontend/src/components/today/`):
   - `DriftCard.tsx` — "Where the model is misfiring" + drift alert count + top symbol
   - `FreshSignalsCard.tsx` — "What it might pursue" + opportunity count + top ticker
   - `ResearchCuriousCard.tsx` — "What it's curious about" + pending query count + top hypothesis name (no buttons)
   - `MarketMoodCard.tsx` — "Market mood" + regime label + VIX + SPY 1w
   
   Each card: title (with role description as sub-line), preview data, click-through link. Empty state shows just the role description.

2. `PendingReviewPanel.tsx`:
   - Header: "Pending review · top {N} of {totalPending}"
   - 5 collapsed rows (one-line summary per query)
   - Click row → inline expand with verdict markdown + Approve/Dismiss buttons
   - Footer link "See full queue ({totalPending - 5} more in backlog) →" → `/research?status=pending`

3. Refactor `Today.tsx`:
   ```
   ┌──────────────────────────────┐
   │ Page header + Run Now button │
   ├──────────────┬───────────────┤
   │ DriftCard    │ FreshSignals  │
   ├──────────────┼───────────────┤
   │ ResearchCur  │ MarketMood    │
   ├──────────────┴───────────────┤
   │ TVContextStrip               │
   │ WatchlistDelta               │
   ├──────────────────────────────┤
   │ PendingReviewPanel (top 5)   │
   └──────────────────────────────┘
   ```

4. Remove `ResearchApprovalStrip` import from Today. Keep the file for now (it's still useful in `/research`). Move the inline-approve/dismiss UX into PendingReviewPanel.

5. Hook update: `useResearchQueries` gains optional `{ order: 'score' | 'asked_at', topOnly: boolean }` params; defaults preserve existing behaviour.

**Reuses:**
- `frontend/src/components/today/{DriftBanner,FreshSignalsStrip,TVContextStrip,WatchlistDelta}.tsx` — drift card wraps existing banner logic; fresh signals card wraps existing strip
- `frontend/src/components/dashboard/RegimeStrip.tsx` for the MarketMood card data
- `frontend/src/components/research/EvidenceItemRow.tsx` for expanded-row evidence rendering
- `useApproveResearchQuery` / `useDismissResearchQuery` mutations unchanged

### Phase 3 — Docs (~1h)

1. `.claude/status/roadmap-shipped.md` — retro entry
2. `.claude/modules/research.md` — ranking formula + auto-age behaviour
3. `.claude/frontend/pages.md` — new Today layout
4. `.claude/status/backlog.md` — close-out for the "noise on Today" implicit deferred item

## Files touched

**Phase 1:**
- New: `migrations/versions/0027_research_query_scoring.py`
- New: `app/research/ranking.py`
- New: `tests/test_research_ranking.py`
- Edit: `app/research/models.py` (3 new columns)
- Edit: `app/research/routes.py` (2 new query params)
- Edit: `app/research/service.py` (compute initial score on create)
- Edit: `app/admin/retention.py` (call ranking.auto_age_expired in sweep)
- Edit: `tests/test_retention_sweeps.py` (add age-out coverage)

**Phase 2:**
- New: `frontend/src/components/today/{DriftCard,FreshSignalsCard,ResearchCuriousCard,MarketMoodCard,PendingReviewPanel}.tsx`
- Edit: `frontend/src/pages/Today.tsx`
- Edit: `frontend/src/hooks/use-api.ts` (extend `useResearchQueries` signature)
- Edit: `frontend/src/lib/types.ts` (extend query param shape if needed)

**Phase 3:**
- Edit: `.claude/status/roadmap-shipped.md`
- Edit: `.claude/modules/research.md`
- Edit: `.claude/frontend/pages.md`
- Edit: `.claude/status/backlog.md`

## Verification

After each phase:
1. `unset API_KEY DATABASE_URL && ./venv/bin/python -m pytest -q` — green
2. `cd frontend && npx tsc --noEmit` — clean
3. Manual smoke against running stack (already up on :3000)

End-to-end after Phase 2:
- Open `/` → 2×2 grid renders, all four cards have role descriptions
- Pending review panel shows top 5 by score (verify against `curl /v1/research/queries?status=pending&order=score&limit=5`)
- Click a row → inline expand shows verdict, Approve/Dismiss buttons present
- Approve → row removes from top-5, next-best deferred query climbs in
- Pending query created 31+ days ago → status flips to `dismissed` after retention loop fires

## Decisions locked

| Decision | Value |
|---|---|
| Visible cap | 5 |
| Ranking | server-side composite score |
| Auto-age threshold | 30 days |
| Auto-age action | dismiss with `auto-aged-out` reason |
| Grid shape | 2×2 symmetric |
| Inline actions on Today | NO — buttons only inside the expanded pending-review row |
| Where dismissed queries land | `/research?status=dismissed` (unchanged) |
| Manual `/research/ask` queries | go through same ranking; no special treatment |
| Score recompute cadence | on-create + on-status-change + nightly via retention loop |

## What this does NOT change

- Research weekly auto-loop cadence (operator separately decides; stays as-is)
- The Research page itself (`/research`) keeps its current layout
- Backend API surface for approve/dismiss is unchanged
- Existing `ResearchApprovalStrip` component file kept for `/research` reuse; just removed from Today
