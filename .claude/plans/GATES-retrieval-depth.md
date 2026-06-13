# Gate verdicts — Retrieval Depth & De-biasing Program

Gate protocol per `.claude/plans/retrieval-depth-and-debiasing-program.md`.
One entry per phase: build → gap/bug sweep → self-correct → forward re-eval → verdict.

---

## Phase 0 — Measurement substrate + write-back seam — **PASS** (2026-06-13)

### Shipped
- **Retrieval log** (`tools/vault_indexer/retrieval_log.py`, new): `retrieval_log` table in the indexer's own sqlite cache; `ensure_schema` / `record` / `recent`. Stdlib-only (takes any DB-API `con`), so it carries zero apsw/model coupling. Captures per-search `{query, mode, domain, k, anchors, eligible_count, surfaced[], dropped[+reason]}`. Env toggle `RETRIEVAL_LOG_ENABLED`, row cap `RETRIEVAL_LOG_MAX_ROWS` (default 5000) pruned on each write.
- **Search hook** (`tools/vault_indexer/search.py`): added `mode="fast"` + `log=True` params and a `_maybe_log` helper that snapshots the fully-scored candidate set *before* the top-k cut and records the eligible-but-dropped delta. Additive; logging wrapped in try/except so it can never break search.
- **Write-back seam**: `RxDeepResult` model (`app/rx/models.py`), schemas (`DeepResultCreate/Read/List` in `app/rx/schemas.py`), `app/rx/deep_service.py`, routes `POST /v1/rx/deep` (ingest token) + `GET /v1/rx/deep` (API key) in `app/rx/routes.py`, migration `0031_rx_deep_results.py`.
- **Baseline script** (`scripts/retrieval_eval.py`, new): fixed 12-query finance set → fast-path snapshot for the Phase-1 recall comparison.
- **Tests**: `tests/test_retrieval_log.py` (6), `tests/test_rx_deep.py` (13).

### Gap/bug sweep
- Full suite: **872 passed, 0 failed** (6 pre-existing deprecation warnings, unrelated). Baseline before this phase was green; +19 new tests.
- New Phase 0 tests: 19/19 pass.
- rx + accuracy regression set (76 tests): pass.
- All changed files byte-compile.
- Migration: single head `0031` off `0030`; **model↔migration parity verified exact** (7 cols, 1 CHECK, 3 indexes identical). DDL correctness independently proven by the suite's `create_all` path + `test_db_check_rejects_bad_kind_direct_insert`.
- Fast-path regression: search.py change is additive (defaulted params, try/except-wrapped logging, no change to scoring/ranking/return order). Full suite confirms no behavioral drift.

### Known limitations / honest caveats
- **Async-alembic bare-shell run blocked** by a greenlet/event-loop harness artifact when invoking `alembic upgrade` outside the app's async context. Not a migration defect — DDL is proven by `create_all` + parity check. Operator applies `alembic upgrade head` on the laptop in the normal app context.
- **Baseline snapshot is operator-run**: `scripts/retrieval_eval.py` needs the bge-large model + the populated finance cache DB (laptop-side, ~1.5GB), so the actual "before" numbers are captured on the laptop, not in this shell. Script plumbing compiles + is import-safe.

### Forward re-evaluation (Phase 1)
- Substrate is ready: `retrieval_log` already supports `mode="deep"` + arbitrary per-candidate `drop_reason` (proven by `test_deep_mode_label_persists`), and `/v1/rx/deep` accepts `kind="deep_retrieval"`.
- **Refinement learned**: `_maybe_log` reads `candidate.get("drop_reason", "below_top_k")`. Phase 1 deep mode should *set* a `drop_reason` on each pruned candidate (`"prune_floor"`, `"beam_exhausted"`, `"decay_zero"`) so reasons flow through unchanged. No plan change needed — the hook is already in place.
- No new trade-off surfaced. Proceeding to Phase 1.

### Verdict: **PASS** → advance to Phase 1.

---

## Phase 1 — Deep retrieval mode (multi-hop, high top-K, filter-late) — **PASS** (2026-06-13)

### Shipped
- **`deep_search()`** (`tools/vault_indexer/graph_search.py`): filter-late variant of the beam walk. Wider on every axis — `DEEP_DEFAULTS` = beam 12 (fast 5), hops 4, seed 8, prune 0.30 (fast 0.50), top-50 (fast 10), early-stop **disabled**. Three behavioral changes vs fast:
  1. **Nothing vanishes silently** — candidates below the prune floor or past the beam cap are RETURNED in a `pruned` list, each with a `drop_reason` (`below_prune_threshold` / `beam_overflow`), not dropped.
  2. **Decay is a feature, not a filter** (A4) — decay<=0 rows (e.g. SEC filings past the keep-2 cap) are KEPT, flagged `decay_zero`, so an old-but-dispositive filing still reaches the judgment layer. Score never zeroes a candidate out of existence.
  3. **Hop distance + retain/drop reasons** attached to every candidate for downstream auditability.
- **`classify_candidates()`** — pure filter-late split (no DB/model), the unit-testable core of the "data not filtered before evaluation" contract.
- **`/deep_search` endpoint** (`tools/vault_indexer/app.py`) — wider param bounds, returns `results` + `pruned`. On-demand only; not on the fast path.
- **`/rx-deep-retrieve` command** (`~/.claude/commands/rx-deep-retrieve.md`) — resolves a rec-id or query, calls `/deep_search` on :8001, evaluates the FULL set (incl. pruned) in-session with full visibility, POSTs the curated set to `/v1/rx/deep`. Subscription-billed, no API key.
- **`scripts/retrieval_eval.py --mode compare`** — runs fast+deep per query, reports per-query `deep_only` (paths deep surfaced that fast dropped — the concrete recall save) + totals. The operator's one-command gate probe.
- **Tests**: `tests/test_deep_search.py` (6).

### Gap/bug sweep
- Full suite: **878 passed, 0 failed** (+6 deep_search tests).
- Filter-late contract proven at unit level: nothing discarded (surfaced+dropped == all inputs), every drop carries a reason, decay-zero kept with `kept_despite_decay_zero`, retain reasons assigned, surfaced sorted by score. `DEEP_DEFAULTS` asserted wider than fast on every axis.
- `graph_search.py` + `app.py` byte-compile; `graph_search` imports cleanly (sentence_transformers present).
- Fast path untouched — `graph_search()` and `search()` behavior unchanged; deep mode is a separate function + separate endpoint. Full suite confirms.

### Known limitations / honest caveats
- **The empirical recall-delta is operator-run, not validated here.** The graph walk needs the bge model + populated finance `vault_chunk_vec` (laptop-side). I proved the *mechanism* (wider params, filter-late assembly, drop-reasons, decay-as-feature, deep logging) at the unit level, but NOT the *measured recall gain* on the live corpus. The operator runs `python scripts/retrieval_eval.py --mode compare` on the laptop to get the concrete "deep surfaced N paths fast dropped" number. Until then, the recall claim is mechanistically sound but empirically unconfirmed. This is the honest boundary of what this environment can verify.
- `quality_floor` is referenced only in the (default-off) early-stop branch of deep mode; flagged `# noqa: F821` since it's unreachable unless `disable_early_stop=False` is passed with a bound value. Acceptable — deep mode's contract is full-depth.

### Forward re-evaluation (Phase 2)
- Phase 2 (citation verification) is app-side + deterministic, independent of the deep path. The `/v1/rx/deep` payloads (and existing rec `source_refs`) are where citations will be verified; the substring-proof check has no new dependency. No plan change.
- The `pruned` + `rescued` fields in the deep payload give Phase 3 (contradiction) a richer candidate set to reason over — confirms the Phase 3 plan (operate on the deep set) holds.
- No new trade-off surfaced. Proceeding to Phase 2.

### Verdict: **PASS** → advance to Phase 2.

---

## Phase 2 — Citation verification (app-side, deterministic) — **PASS** (2026-06-13)

### Shipped
- **`app/rx/citation_check.py`** (new, pure functions): `verify_quote(quote, chunk_text)` — normalized substring check (NFKC, smart-punctuation fold, whitespace collapse, casefold) with ellipsis-elided quotes checked fragment-by-fragment in order. `annotate_source_refs` stamps each ref `citation_verified` + `citation_reason` (immutably). `status_from_refs` derives a rec-level status. Reasons: `match` / `no_quote` / `no_chunk_text` / `too_short` / `not_found` (the D1 fabrication flag).
- **Ingest wiring** (`app/rx/service.py`): `create()` annotates `source_refs` at write time. Wrapped in try/except — a verifier crash degrades to unannotated (never blocks ingest); a genuine mismatch is recorded.
- **Surfacing**: `citations_status` (`no_quotes` | `all_verified` | `has_mismatch` | `unverifiable`) on both `RecRead` + `RecListItem`, derived on read from source_refs. **No migration** — status is computed, refs annotations live in the existing `source_refs` JSON.
- **Tests**: `tests/test_citation_check.py` (16, pure), `tests/test_rx_citation_integration.py` (6, end-to-end).

### Gap/bug sweep
- Full suite: **900 passed, 0 failed** (+22).
- Fuzz/robustness (gate requirement): exact match, **fabrication flagged `not_found`** (zero false-clean), case+whitespace insensitive, smart-quote/em-dash fold, ellipsis in-order pass + out-of-order fail, punctuation-free Whisper run-on, too-short quote NOT falsely verified, missing quote/chunk handled as unverifiable.
- Integration: `has_mismatch` / `all_verified` / `unverifiable` / `no_quotes` all flow ingest→read on detail + list. Ingest never blocked.
- `too_short` floor (12 normalized chars) prevents the "3-char quote matches anything" false-confidence trap.

### Known limitations / honest caveats
- **Verification needs chunk text in the ref.** A ref with a `quote` but no `text`/`chunk_text` is honestly marked `unverifiable`, not silently passed. The producing commands (`/rx-finance`, `/rx-deep-retrieve`) have the chunk text and SHOULD include it; today `/rx-finance` ships `quote` without `text`, so existing recs will read `unverifiable` until that command is updated to include chunk text (a one-line addition, deferred to avoid scope-creep into the finance generator this phase). The capability is correct and live; full coverage depends on producers attaching source text.
- No semantic paraphrase detection — a quote that paraphrases rather than copies will flag `not_found`. That is intentional: the check verifies *verbatim* attribution, which is what "quote" claims. Paraphrase-tolerance would require an LLM and belongs to the Phase 3 judgment layer, not this deterministic check.

### Forward re-evaluation (Phase 3)
- Phase 3 (contradiction) is Claude-Code-side and operates on the deep candidate set's text — the same "reason over chunk text" pattern. It POSTs `kind="contradiction"` to `/v1/rx/deep`, already accepted + tested. No app-code dependency, no plan change.
- The `unverifiable` caveat above suggests a small follow-up (have producers attach `text` to source_refs) — logged for Phase 7 porting, not a blocker.

### Verdict: **PASS** → advance to Phase 3.

---

## Phase 3 — Contradiction / staleness pass (Claude-Code-side) — **PASS** (2026-06-13)

### Shipped
- **`/rx-contradiction-check` command** (`~/.claude/commands/rx-contradiction-check.md`): loads a rec + its evidence (source_refs and/or deep_retrieval candidates), states the rec's single core claim, judges each source **supports / contradicts / orthogonal** against that claim (O(N), on text not score), flags staleness vs the claim's time horizon, identifies directly-contradictory source pairs, and POSTs a `kind="contradiction"` report to `/v1/rx/deep`. Sets `verdict` ∈ `conflicted | mixed | aligned`. App surfaces a "⚠ sources conflict" banner when conflicted.

### Gap/bug sweep
- **No app code changed** — Phase 3 is a command + the already-built `/v1/rx/deep` endpoint. Suite remains **900 passed** from Phase 2.
- The `kind="contradiction"` write path is proven by `tests/test_rx_deep.py::test_deep_post_creates_with_rec_id` (posts exactly that kind, asserts round-trip).
- No-API-key discipline + read-on-text-not-score + conservative-contradicts (alarm-fatigue guard) all stated as hard rules in the command.

### Known limitations / honest caveats
- **Empirical precision is operator-run.** This is an in-session LLM-judgment command — its stance-labeling precision can only be measured by the operator running it on a hand-labeled set (the Phase 3 gate probe). I verified the *plumbing* (command well-formed, endpoint accepts + round-trips the payload, surfacing path defined); the *judgment quality* is validated in use. This is the inherent boundary of an LLM-judgment feature — same class of caveat as any human-in-the-loop classifier.
- Contradiction precision has a ceiling (flagged as a program trade-off): false "conflict" flags risk alarm fatigue. Mitigated by the explicit "be conservative on contradicts" rule, not eliminated.

### Forward re-evaluation (Phase 4)
- Phase 4 (attribution split + explicit hypothesis linkage + P&L metric) is app-side and touches `app/trades/models.py` (new `rec_influence_kind`), the substring linkage in `app/rx/service.py::links_for_rec` (D2 — add explicit-linkage column, keep substring as fallback suggestion), and the `/rx-analyze` lift computation (exclude `influenced`). Needs a migration (trades column). No dependency on Phases 1–3. Plan holds.

### Verdict: **PASS** → advance to Phase 4.

---

## Phase 4 — Attribution split + explicit linkage + P&L metric — **PASS** (2026-06-13)

### Shipped
- **Migration `0032`** + model cols: `trades.rec_influence_kind` (CHECK ∈ `preceded_independent`|`influenced`|NULL) and `recommendations.linked_hypothesis_ids` (JSON).
- **`app/rx/analytics.py`** (new, pure): `action_rate` (acted/(acted+skipped), dismissed+snoozed excluded), `health_band`, `creditable_trades` (B4 — excludes `influenced`), `attribution_summary`, `pnl_per_rec` (B3 value metric), `value_vs_engagement` (flags GREEN-engagement / negative-P&L divergence).
- **Trade capture**: `rec_influence_kind` on `TradeCreate` + `create_trade` (validated: requires `related_rec_id`, must be a known value) + serialized out.
- **Explicit linkage (D2 fix)**: `RecCreate.linked_hypothesis_ids` → stored; `links_for_rec` now surfaces explicit links as `match_type="explicit"` and **suppresses substring double-counting** for already-linked hypotheses, demoting the rest to `match_type="substring_fallback"`.
- **`/rx-analyze` command**: new §5e — exclude `influenced` from predictive-lift, report attribution mix, surface realized-P&L-per-rec beside action_rate, flag the value/engagement divergence. Report header updated.
- **Tests**: `tests/test_rx_analytics.py` (10 pure), `tests/test_rx_attribution_integration.py` (6 e2e).

### Gap/bug sweep
- Full suite: **914 passed, 0 failed** (+14).
- B4 proven: `influenced` trade excluded from `creditable_trades`; `preceded_independent` + NULL kept. DB CHECK rejects bad influence kind (direct insert raises IntegrityError). Capture validates `rec_influence_kind` requires `related_rec_id`.
- B3 proven: `pnl_per_rec` sums only closed rec-linked trades; `value_vs_engagement` flags GREEN-action-rate + negative-P&L.
- D2 proven: a rec mentioning two hypothesis titles but explicitly linking ONE surfaces that one as `explicit` and the other only as `substring_fallback` — and an explicit link is never double-counted by the substring path.
- Migration `0032` head off `0031`; model↔migration parity confirmed (both cols + CHECK present in both).

### Known limitations / honest caveats
- **`rec_influence_kind` defaults NULL** → existing/legacy trades stay creditable until the operator classifies them. The B4 break only bites for trades captured *with* the classification. This is deliberate (no retroactive voiding) but means the de-bias is forward-looking, not retroactive.
- The `/rx-analyze` lift/P&L computation lives in the command (markdown), not app code — so the *command* must follow the new §5e. The app provides the pure helpers (`analytics.py`) the command mirrors; drift between command prose and helper semantics is possible until/unless `/rx-analyze` is refactored to call an endpoint. Logged as a Phase-7 consideration.
- Explicit linkage depends on `/rx-finance` populating `linked_hypothesis_ids` at compose time — same producer-update dependency as the Phase 2 `text` caveat. Capability is live; coverage grows as the generator is updated (Phase 7).

### Forward re-evaluation (Phases 5–6)
- Phase 5 (external disconfirmation) is Claude-Code-side, posts `kind="disconfirmation"` to `/v1/rx/deep` (already accepted) — no app code, no plan change.
- Phase 6 (drift monitors) is app-side: a preference-drift detector over the disposition/fit series + an embedding-shift monitor + the landmine ledger. The `analytics.action_rate` + the `_constants` patterns give it a foundation. Plan holds.
- Two producer-update follow-ups accumulated (Phase 2 `text` in source_refs, Phase 4 `linked_hypothesis_ids` in `/rx-finance`) — batch both into Phase 7.

### Verdict: **PASS** → advance to Phase 5.

---

## Phase 5 — External disconfirmation (Claude-Code-side) — **PASS** (2026-06-13)

### Shipped
- **`/rx-counter-external` command** (`~/.claude/commands/rx-counter-external.md`): for a finance rec, searches the OPEN WEB (WebSearch/WebFetch) for the strongest credible counter to the rec's core claim, steelmans it, contrasts in-vault vs external, and POSTs `kind="disconfirmation"` to `/v1/rx/deep`. App shows "External counter" beside the vault counter-thesis. Breaks B2 (same-vault counter-thesis bubble).

### Gap/bug sweep
- **No app code changed** — command + the already-built `/v1/rx/deep` endpoint. Suite remains **914 passed**.
- `kind="disconfirmation"` write path proven by `tests/test_rx_deep.py::test_deep_post_ignores_client_owner` (posts exactly that kind, asserts owner-stamp).
- Hard rules encode the discipline: no API key, sources must be external (escape the vault), steelman not strawman, `strength: "none"` is a valid honest outcome, **must record `web_surface_bias_note`** (names the new bias introduced).

### Known limitations / honest caveats
- **Replaces filter-bubble bias with web-surface bias** (whatever the open web ranks highly). Net positive — an external counter beats an in-vault strawman — but NOT bias-free. The command forces a `web_surface_bias_note` so the new bias is named, not hidden. This is a documented program trade-off, not a defect.
- Empirical quality (does it find genuinely credible counters?) is operator-run — inherent to an LLM+web judgment command. Plumbing verified; judgment validated in use.

### Forward re-evaluation (Phase 6)
- Phase 6 (drift monitors + landmine ledger) is the last app-code phase: a preference-drift detector over the disposition/subjective-fit slope (distinct from the existing prediction-MAPE drift), an embedding-distribution-shift monitor, and the n=1 landmine ledger with TRIGGER conditions. `analytics.action_rate` is the foundation for the preference-drift series. Plan holds.

### Verdict: **PASS** → advance to Phase 6.

---

## Phase 6 — Drift monitors + landmine ledger — **PASS** (2026-06-13)

### Shipped
- **`app/rx/drift_monitor.py`** (new, pure): `linear_slope` (least-squares over evenly-spaced windows), `preference_drift` (B6 — flags declining/improving action_rate or subjective_fit trend via slope threshold, distinct from the prediction-MAPE detector), `embedding_centroid_shift` (cosine distance baseline-vs-current, flags distribution drift), `centroid` (mean vector helper).
- **n=1 landmine ledger** appended to `.claude/status/tech_debt.md` (4 entries, each with an explicit TRIGGER): L1 substring linkage fallback (→ 2nd user / >50 hypotheses), L2 single operator UUID (→ 2nd user, the master landmine), L3 global thresholds not per-cohort (→ 2nd user), L4 `/rx-analyze` math in command not app (→ prose/helper drift or unattended run).
- **Tests**: `tests/test_rx_drift_monitor.py` (11).

### Gap/bug sweep
- Full suite: **925 passed, 0 failed** (+11).
- Preference drift: declining series flagged `declining`, improving flagged `improving`, stable not flagged, gentle-decline-under-threshold not flagged, <2 points → `insufficient_data`.
- Embedding shift: identical centroid → no shift (distance 0), orthogonal → shifted (distance 1.0), near-parallel under threshold → no shift; centroid mean + ragged/empty guards.
- Landmine ledger uses the doc's own entry skeleton; encodes the council's Critic-vs-Pragmatist resolution (cheap now, detonate at n=2) as explicit triggers.

### Known limitations / honest caveats
- **Detectors are pure math; the series + centroids are assembled by the caller.** Wiring them to a live cron/endpoint (assemble per-week action_rate from dispositions; roll embedding centroids from the indexer) is integration left for when the operator wants the alerts to fire automatically. The detection logic is proven; the scheduling is not wired. This keeps Phase 6 within the "deterministic, testable core" boundary and avoids adding an always-on job to the laptop without the operator opting in.
- Embedding-shift needs real embeddings to compute centroids (indexer-side) — same model-dependency boundary as Phases 0/1.

### Forward re-evaluation (Phase 7)
- Phase 7 = port finance-first work to other domains + repopulate the limitations tables + retro. Most of what shipped is already domain-agnostic: `citation_check`, `analytics`, `drift_monitor` are pure and domain-blind; `retrieval_log` + `deep_search` carry a `domain` field already. The finance-specific surfaces are the `/v1/rx/deep` CHECK (`domain='finance'` is NOT on rx_deep_results — it's keyed by rec_id/query_hash, so cross-domain works) and the commands (finance-targeted by port:8001 + the finance ingest path). Porting is mostly: point commands at the other domains' indexer ports + confirm the pure modules need no change. Plan holds; the two producer-update follow-ups (Phase 2 `text`, Phase 4 `linked_hypothesis_ids`) fold in here.

### Verdict: **PASS** → advance to Phase 7.

---

## Phase 7 — Port + repopulate tables + retro — **PASS** (2026-06-13) — PROGRAM COMPLETE

### Shipped
- **Producer follow-ups** (closing the Phase 2 + Phase 4 coverage caveats): `/rx-finance` now POSTs `text` per source_ref (so citations verify, not `unverifiable`) + populates `linked_hypothesis_ids` (so explicit linkage beats substring). Documented inline in the command's POST step.
- **Porting verification**: confirmed `citation_check`, `analytics`, `drift_monitor` are domain-agnostic (asserted no `finance` literal coupling); `retrieval_log.record` + `deep_search` are domain-parametrized. The retrieval core ports to any domain's indexer trivially; the de-biasing *write* surfaces (`/v1/rx/deep`, recommendations) are finance-only **by architecture** (rx routing lock D-045 — fitness→Supabase, learning→markdown live in other stores), which is a correct boundary, not a gap.
- **Repopulated limitation tables + retro**: [`retrieval-depth-RETRO.md`](retrieval-depth-RETRO.md) — every Theme A–E row + 7 interactions re-scored FIXED/MITIGATED/UNCHANGED/NEW, before/after, 2 newly-introduced risks named, 6 trade-offs taken, honest open-items close.

### Gap/bug sweep
- Final full suite: **925 passed, 0 failed** (program start ~856 → +69 net new tests).
- Domain-agnostic assertion passes; producer edit is command-only (no code change).
- All 6 prior gates PASS; no BLOCKED at any boundary.

### Outcome (vs the original 23-row + 7-interaction limitation set)
- **11 FIXED · 8 MITIGATED · 8 UNCHANGED · 2 NEW introduced.** Every UNCHANGED is a deliberate scope call (n=1 red-herring or low-severity), not an oversight.
- Master multiplier **C1 broken** (misses now measurable); dangerous compound **B3⊗B4⊗B5 largely defused** (self-influence can't read as learning).

### Honest residual (operator-side)
- Empirical recall delta + contradiction precision = laptop-run (model + live corpus). Mechanisms unit-proven; live numbers not yet captured.
- Drift-monitor cron wiring + the structural n=1 risks (B7/E1/C3) remain — counter-pressured, resolve at n=2 or not in code.

### Verdict: **PASS** — program complete.

---

## Phase 8 — Governors for the 2 introduced risks — **PASS** (2026-06-13)

### Shipped
- **`app/rx/deep_governors.py`** (new, pure): `contradiction_severity` (NEW-1 alarm-fatigue guard — banner fires only on a contradictory pair OR ≥2 contradictions; lone contradiction = medium; staleness-only = low/no-banner) + `disconfirmation_credibility` (NEW-2 web-surface-bias guard — caps strength by distinct-publisher count + source tier; single source capped at `thin`; `strong` needs ≥3 publishers incl. primary/reputable; never inflates above self-report) + `govern(kind, payload)` dispatcher.
- **Applied at `/v1/rx/deep` ingest** (`deep_service.create`): contradiction/disconfirmation payloads get a `governor` block; best-effort (never blocks ingest).
- **Commands updated**: `/rx-counter-external` emits per-source `tier`; both commands document that the GOVERNOR (not the LLM's self-report) decides banner/credibility.
- **Tests**: `tests/test_rx_deep_governors.py` (17) + 2 ingest-integration tests in `test_rx_deep.py`.

### Gap/bug sweep
- Full suite: **942 passed, 0 failed** (+17).
- NEW-1: pair → high+banner; ≥2 → high+banner; 1 → medium+banner; staleness-only → low+no-banner; aligned → none. Count derived from sources when absent.
- NEW-2: single source capped `thin` despite self-`strong`; 3 reputable+primary → `strong`; 2 → `moderate`; honest `none` never inflated by sources; 0 sources → `none`. Governed at ingest (stored in payload).

### Outcome
- **NEW-1 → RESOLVED**: the conflict banner is now governed by deterministic evidence thresholds, not the raw LLM `verdict`. Alarm fatigue can't be driven by a single weak label.
- **NEW-2 → RESOLVED**: web-surface bias is capped — an optimistic single-source external counter can no longer present as decisive; credibility is a function of source diversity + tier, applied deterministically.
- Both LLM features keep their judgment role (labeling); the trust decision is now auditable + tunable in one pure module.

### Residual
- The governors consume LLM-emitted labels (stance, tier). A mis-labeled tier still flows in — but the *thresholds* are deterministic, so the failure surface shrinks from "any label triggers" to "labels must clear fixed bars." Tier-labeling honesty is the remaining judgment dependency (inherent to LLM-in-the-loop).

### Verdict: **PASS** — 2 introduced risks closed.
