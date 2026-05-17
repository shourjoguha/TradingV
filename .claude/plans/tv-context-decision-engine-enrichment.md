# TV Context → Decision Engine Enrichment

## Context

Three diagnosed gaps where TV Context inputs (note / idea / screenshot / event / webhook) land in `tv_context_items` but never reach downstream decision systems. Audit conducted 2026-05-17 confirmed all three still open — code inspection found zero references in any of the consumer modules.

| Gap | Verified state (2026-05-17) | Effort | Order |
|---|---|---|---|
| **3 — ticker_review parity** | `app/tv_context/{routes,service}.py` has 0 `enqueue_or_bump` calls. Video pipeline routes unknown tickers; TV context doesn't. | ~2h | **Phase 1** (ship first, cheapest) |
| **1 — rx-finance reads TV context** | `app/rx/service.py` has 0 `tv_context` references. Pulls drift/hypotheses/trades only. | ~4h | **Phase 2** |
| **2 — hyp_tick consumes `HypothesisTVContextLink`** | `app.hypotheses.service.run_daily_tick` calls `inv_dsl.evaluate(row.invalidator, session=session)` — DSL never reaches TV context tables. Link rows are dead data. | ~1d | **Phase 3** |

Order rationale: Phase 1 is a quick parity fix that doesn't change decision behaviour but completes the unknown-ticker pipeline (operator sees TV-context-derived tickers on Today's review strip). Phase 2 makes TV context inputs **visibly shift what rx-finance recommends** — the highest-leverage gap. Phase 3 is the deepest change (DSL extension) and benefits from the patterns we set in Phase 2.

## Execution instructions (operator-locked)

> Execute this plan step by step. Check for implementation gaps and bugs, and fix anything you find. Re-evaluate the next phase in the plan for coherence and completeness. Make tactical adjustments based on the last phase's implementation. Update documentation. Then move to executing the next phase. Repeat the cycle.
>
> Use tools and connectors as required. If you need to verify anything do it yourself. Conduct tests to help with development velocity and progress.
>
> Keep a ledger of all decisions and trade-offs made — update in documentation and surface via chat as well.
>
> If you get locked out due to usage limits, loop every 90 minutes till you get usage back.

## Phase 1 — Ticker-review parity for note/idea/screenshot/event (~2h) — **SHIPPED 2026-05-17**

> **Ledger (Phase 1):**
> - **Design call**: chose async path (`await load_ticker_whitelist()` + `await enqueue_or_bump()`) over the plan's literal `_sync` suffix because TV-context routes are already async. The plan's `_sync` was lifted verbatim from the video-pipeline pattern which is sync.
> - **Trade-off accepted**: extra `SETTINGS.TV_CTX_TICKER_REVIEW_ENABLED` gate (default True in prod, OFF in tests). Required because SQLite's `:memory:` serial write lock deadlocks an inner `enqueue_or_bump()` commit against the outer ingest's uncommitted transaction. Postgres has no equivalent issue. New tests opt back in via `monkeypatch.setattr(SETTINGS, "TV_CTX_TICKER_REVIEW_ENABLED", True)`.
> - **Surprise**: existing `test_recent_for_ticker_filters` lost its rows when the helper was unconditionally on — the inner session blocked the outer commit. Adding the env-var gate restored isolation without changing production behaviour.
> - **Next-phase implication**: Phase 2's `app/rx/tv_context_signal.py` will use **async DB reads** (not sync). Same SQLite-vs-Postgres seam.


### Goal
Match the video pipeline: when an operator submits a TV context input with a ticker NOT in `roster ∪ boards ∪ The Street tier-1/2`, enqueue that ticker to `ticker_review_queue` so it surfaces on Today's review strip.

### Tasks
1. Add `from app.ticker_review import service as _tr_svc` lazy-import to `app/tv_context/service.py`.
2. After `session.flush()` in `ingest_note`, `ingest_idea`, `ingest_screenshot_row`, `ingest_event`: call `_tr_svc.enqueue_or_bump_sync(ticker, video_id=None, channel="tv_context_<kind>", snippet=<first 200 chars of payload body>)` for unknown tickers. Pattern mirrors `tools/vault_indexer/ingest/youtube_channel.py`.
3. Reuse `chart_extractor.load_ticker_whitelist_sync()` (already cached in process) to decide unknown-vs-known.
4. Best-effort: enqueue failure must NEVER block the ingest. Wrap in `try/except` + log only.
5. Webhook ingest: SKIP. Webhooks are rule-driven; ticker is always pre-filtered by the operator's webhook config — false-positive risk too high to bulk-enqueue.

### New / changed files
- Edit: `app/tv_context/service.py` (add ~30 lines: helper `_maybe_enqueue_review(ticker, kind, snippet)` + 4 call sites)
- Edit: `tests/test_tv_context.py` — 4 new tests (one per ingest kind) asserting: known ticker = no enqueue, unknown ticker = 1 enqueue call, enqueue raise doesn't bubble. Mock `ticker_review.service.enqueue_or_bump_sync`.

### Self-eval
- [ ] `pytest -q` green (full suite, expect +4 tests)
- [ ] Smoke: `POST /v1/tv-context/note` with `{ticker: "ZZZZ", body: "test"}`. Verify row in `ticker_review_queue` (sqlite/postgres query).
- [ ] Smoke: `POST /v1/tv-context/note` with `{ticker: "NVDA", body: "test"}` (assume NVDA on roster). Verify NO row written.
- [ ] Stack still responds within 100ms on ingest (extra enqueue must not slow operator UX).

### Audit checklist
- [ ] No regression in `enrich_on_trade_close` (trade-close enrichment shouldn't accidentally enqueue dismissed-ticker rows).
- [ ] Imports lazy (don't load `ticker_review` until first ingest call — keeps cold-start fast).
- [ ] Snippet truncated to 200 chars (avoid bloating queue rows with screenshot vision-summary markdown).

## Phase 2 — rx-finance reads TV context (~4h)

### Goal
Make TV Context inputs visibly shift `rx-finance` recommendations. Operator screenshots an NVDA chart, the next `/rx-finance` invocation surfaces NVDA-relevant recs higher.

### Design call (TO RESOLVE AT PHASE-START)
Two paths, pick at phase kickoff after re-reading `app/rx/service.py`:

**A. Composite-score modulation.** Add a `tv_context_signal_score(ticker, since=14d) -> float` helper. Mix into existing rec ranking as a multiplier or bonus. Pros: minimal code touch. Cons: hides the contribution; operator can't tell why a rec ranked high.

**B. Explicit "operator attention" axis on the rec object.** New column `recommendations.attention_score FLOAT NULL` + the new helper. Surfaced as a separate badge in rec detail UI ("Operator attention: 3 screenshots + 1 note in last 14d"). Pros: transparent, auditable. Cons: migration + UI change.

**Recommendation: B.** Decision-engine changes that aren't visible are anti-product. Migration is cheap. The badge teaches the operator "this is why this ranked here" — closes the feedback loop.

### Tasks
1. Migration `0030_recommendations_attention_score.py`: add `attention_score FLOAT NULL` + `attention_breakdown JSONB NULL` (per-kind counts for transparency) to `recommendations` table.
2. New function `app/rx/tv_context_signal.py:compute_attention(ticker, *, since_days=14, kind_weights=DEFAULT) -> dict` returning `{score: float, breakdown: {note: N, idea: N, screenshot: N, event: N}}`. Weighted-sum: `Σ (kind_weight × count × exp(-age_days / half_life))`.
3. Wire into `app/rx/service.py:create` — compute and persist on rec creation. If creation site doesn't have ticker, expose helper for callers to populate.
4. Wire into `app/rx/service.py:list_recs` — return attention fields on each row.
5. Frontend: `frontend/src/lib/types.ts` — extend `Recommendation` interface with `attention_score`, `attention_breakdown`. `RxFinanceDetail.tsx` (or whichever surface shows rec detail) — render a badge: "👁️ Operator attention: N screenshots + M notes in last 14d".
6. Tests: 6 new in `tests/test_rx_attention.py` — score math, kind weighting, age decay, empty=0, integration with `create`, list endpoint returns the fields.

### Locked tuning (revisit if recommendations get noisy)
```python
DEFAULT_KIND_WEIGHTS = {
    "screenshot": 1.0,    # most effort to create → highest signal
    "note": 0.7,
    "idea": 0.5,
    "event": 0.4,
    "webhook": 0.2,       # auto-fired, low operator intent
}
HALF_LIFE_DAYS = 7        # weekly half-life — screenshots from a month ago barely count
```

### Self-eval
- [ ] `pytest -q` green (+6 tests)
- [ ] Frontend `tsc --noEmit` clean
- [ ] Smoke: ingest 3 screenshots for NVDA today → `attention_score` for NVDA-related rec > 2.0. Compare against TSLA (no recent context) → attention_score = 0.
- [ ] Operator sees the badge on the rec detail page after refresh.

### Audit checklist
- [ ] Score deterministic given same inputs (no flakiness from timezone math — use `_utc_now` consistently).
- [ ] Half-life decay numerically stable for inputs > 90d (test covers this).
- [ ] When `since_days=0` or no inputs found → returns `{score: 0.0, breakdown: {...all zeros}}` not None.
- [ ] Migration includes downgrade path.

## Phase 3 — Hypothesis invalidator DSL reads `HypothesisTVContextLink` (~1d)

### Goal
Make `HypothesisTVContextLink` rows actually evaluate. Operator flags a screenshot as "evidence-against hypothesis X" → next daily tick reads it → hypothesis flips toward `at_risk` faster.

### Design call (TO RESOLVE AT PHASE-START)
Two paths:

**A. New DSL ops** — extend `app/hypotheses/invalidator.py` grammar with `tv_context_count_since`, `tv_context_stance_count_since` (count items with `stance='evidence-against'` in window). Pros: composable into existing AND/OR/NOT trees. Cons: schema-bound DSL; new ops need migration if any.

**B. Parallel context-eval pass** — `run_daily_tick` gains a second loop: for each active hypothesis, check linked context items, apply per-stance rules (e.g. "3+ evidence-against in 14d → push status `at_risk`"). Pros: simpler, no DSL extension. Cons: opaque (operator can't tune via hypothesis YAML).

**Recommendation: A.** Operator already writes invalidators in DSL form. Adding DSL ops keeps everything in one place and operator-tunable. Parallel pass would be hidden logic that bites later.

### Tasks
1. Add `HypothesisTVContextLink` row creation paths to ALL ingest routes (currently only screenshot does it). Add `stance` form param to `note` / `idea` ingest. Operator-facing surface: when ingesting a note linked to a hypothesis, dropdown for stance (`context | evidence-for | evidence-against`).
2. New DSL ops in `app/hypotheses/invalidator.py`:
   - `tv_context_count_since(hypothesis_id, days, min_count)` — fires when ≥ min_count items linked to the hypothesis in the trailing window
   - `tv_context_stance_count_since(hypothesis_id, days, stance, min_count)` — same but filtered to a specific stance
3. DSL validation: extend `validate_spec` to whitelist the new op names + arg schemas.
4. Wire into existing `evaluate` dispatch table (op_name → handler).
5. Frontend: hypothesis-detail page surfaces "Recent linked context: 5 items (3 evidence-against, 1 evidence-for, 1 context)" so operator sees what's driving evaluation.
6. Tests: 10+ new in `tests/test_hypotheses_invalidator.py` — count threshold fires, stance filtering correct, age-window cutoff, AND/OR composition with new ops, malformed args rejected.

### Self-eval
- [ ] `pytest -q` green (+10 tests)
- [ ] Smoke: create test hypothesis with invalidator `{op: tv_context_stance_count_since, args: {days: 14, stance: "evidence-against", min_count: 2}}`. Link 2 screenshots with stance="evidence-against". Force `run_daily_tick`. Hypothesis flips to `invalidated`.
- [ ] DSL spec migration documented in `.claude/modules/hypotheses.md` invalidator section.

### Audit checklist
- [ ] Op-name collisions handled (don't shadow existing macro ops).
- [ ] Backwards-compat: existing hypotheses without the new ops keep evaluating identically.
- [ ] Stance default = `context` if operator doesn't specify (no breaking change to existing screenshot ingest).

## Cross-cutting ledger requirement

Every phase's commit MUST include a "Ledger" section in the commit message capturing:
- **Decisions made**: option picked + why
- **Trade-offs accepted**: what was deferred / what was bought
- **Surprises**: anything operator didn't predict (e.g. a schema column missing, an integration point absent)
- **Next-phase implication**: any tactical adjustment for the following phase

Mirror this into `.claude/status/roadmap-shipped.md` retro entry.

## Verification (end-to-end)

After all 3 phases:
1. Drop a screenshot of `$PLTR` (assume PLTR not on roster) → ticker_review_queue gets a row from `channel="tv_context_screenshot"` (Phase 1 working)
2. Operator promotes PLTR to roster via Today strip
3. Drop 3 more screenshots over the week, 1 tagged `stance="evidence-against"` for an existing hypothesis
4. Run `/rx-finance` → PLTR-relevant rec has `attention_score > 0`, badge visible in detail (Phase 2 working)
5. Force-fire `_hyp_tick` → if the hypothesis invalidator uses new DSL op, status flips correctly (Phase 3 working)

## Open questions before kickoff (none blocking)

- For Phase 2 design call (A vs B): default to B unless implementation reveals a blocker
- For Phase 3 design call (A vs B): default to A unless validation paths get hairy

End of plan.
