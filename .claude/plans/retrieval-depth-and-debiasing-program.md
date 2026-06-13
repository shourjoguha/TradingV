# Retrieval Depth & De-biasing Program

**Status:** PLAN (not yet executing)
**Authored:** 2026-06-13
**Scope (operator-confirmed):** Everything — all Tier 1/2/3 recommendations from the limitations retro + a new deep-retrieval capability.
**Write-back seam (confirmed):** new FastAPI endpoint authed with `X-RX-Ingest-Token` (fits the locked dual-auth in `app/rx/routes.py`).
**Domain order (confirmed):** finance first, then port via gated passes.

---

## Governing insight

Split the work along the cost seam the operator identified:

| Tier | Property | Where it runs | Items |
|---|---|---|---|
| **App-side** | cheap, deterministic, always-on, no LLM | TradingV FastAPI + vault_indexer | retrieval log, citation verification, attribution split, P&L metric, drift detectors |
| **Claude-Code-side** | heavy / LLM-judgment / web, on-demand, subscription-billed (NO API key) | this Claude Code session, triggered by an in-app affordance | deep multi-hop retrieval, contradiction pass, external disconfirmation |

The always-on app **never** gains a new per-rec LLM call or heavy compute. Expensive work is opt-in: the app surfaces "run `/rx-<x>` in Claude Code," the session computes it, and results POST back to a new endpoint so the app can display them. This is what makes deep retrieval affordable — it runs where the `<$2/mo` and `<100-embeddings/query` constraints do not apply.

---

## Hard invariants (hold across every phase)

1. `ANTHROPIC_API_KEY` stays **unset**. Claude-Code-side commands use session reasoning + `WebSearch`/`WebFetch` only. Deep retrieval itself is pure Python over the local bge model + sqlite-vec — zero LLM, zero billing.
2. The **always-on app fast path stays cheap and unchanged.** No new per-rec LLM call, no new heavy compute in the request path. Log writes must be cheap/non-blocking.
3. **Single write path preserved.** All writes go through the service layer or the token-authed endpoint. No direct postgres writes from Claude Code.
4. **Finance domain isolation preserved** — the `ck_recommendations_finance_only` CHECK constraint and owner-stamping stay intact.

---

## Gated-pass protocol (applied at the end of every phase)

1. **Implement** to the phase's acceptance criteria.
2. **Gap/bug sweep:**
   - `python -m pytest` green (full suite).
   - Phase-specific failure-mode probe (a planted case that this phase is supposed to catch).
   - Regression check on the always-on fast path: latency + behavior unchanged.
3. **Self-correct:** fix findings, re-run the sweep.
4. **Forward re-evaluation:** re-read the *next* phase's plan against what this phase actually taught us; adjust scope/approach; record any new trade-off that emerged.
5. **Gate verdict:** `PASS` / `PASS-WITH-FIXES` / `BLOCKED`, written with evidence to `.claude/plans/GATES-retrieval-depth.md`.
6. **Advance** only on PASS / PASS-WITH-FIXES. `BLOCKED` → stop and surface to operator.

---

## Phases

### Phase 0 — Measurement substrate + write-back seam (infra; unblocks everything)
**Why first:** C1 (no recall ground truth) is the master multiplier — it makes every other retrieval limitation *unmeasurable*. Build the instrument before optimizing, so every downstream gate is evidence-based and so we can prove whether deep retrieval actually helps.

**Ships:**
- `retrieval_log` table + hook in `tools/vault_indexer/search.py`: per query, capture `{query, anchors, eligible_candidate_pool, retrieved_set, surfaced_set, scores, hop_distances, mode (fast|deep), domain, ts}`. Cheap, append-only, with a retention cap.
- Write-back endpoint skeleton: `POST /v1/rx/deep` (X-RX-Ingest-Token) + `GET /v1/rx/deep` (X-API-Key) + `rx_deep_result` table keyed by rec_id or query_hash, holding a typed payload (`deep_retrieval` | `contradiction` | `disconfirmation`).
- `scripts/retrieval_eval.py`: runs a fixed finance query set through the current fast path and snapshots results as the **baseline "before"** for later recall comparison.

**Acceptance:** every search logs eligible-vs-surfaced; endpoint round-trips a payload (rejects bad token, accepts good); baseline snapshot saved.
**Gate probe:** confirm the log shows a non-trivial eligible⊃surfaced delta on a sample query (proves the instrument can see misses).

---

### Phase 1 — Deep retrieval mode (the headline ask: more hops, higher top-K, filter late)
**Principle:** *separate retrieval from filtering.* Retrieve wide, attach metadata, let the judgment layer (running in Claude Code where LLM judgment is ~free) do the filtering with full visibility — so nothing is dropped before evaluation.

**Ships:**
- `deep` mode in `tools/vault_indexer/graph_search.py`:
  - `beam_width` ~12 (from 5), `max_hops` ~4, `target_k` ~50 (from 10).
  - `prune_threshold` lowered to ~0.30 (floor only, to drop pure noise) — was 0.50.
  - early-stop `quality_floor` **disabled** in deep mode (was 0.65) so it doesn't bail at hop-1.
  - **decay-truncation deferral:** in deep mode do NOT hard-drop filings-beyond-2 or apply the ladder floor as a cut (addresses A4); attach decay as a *feature* on each candidate instead.
  - candidates returned **with metadata**: similarity, hop distance, decay weight, lexical-hit flag, retain-reason.
- `/rx-deep-retrieve <rec-id|query>` Claude Code command: runs deep mode, ranks + filters with full visibility, POSTs the curated set to `/v1/rx/deep`. Pure-Python retrieval = no API.
- App affordance: when fast-path `thesis_match` is weak (score < threshold) or corpus is sparse, surface "Deep retrieval available — run `/rx-deep-retrieve <rec-id>` in Claude Code."

**Acceptance:** deep mode returns ≥ target_k candidates with metadata; on a planted query where the fast path missed a known-relevant doc, deep mode surfaces it; results POST back and the app shows them.
**Gate probe:** recall delta via the Phase-0 log — deep vs fast on the finance query set (how many eligible docs deep surfaced that fast dropped); confirm **every dropped candidate has a logged reason** (no premature/silent filter); confirm memory stays within laptop budget interactively.

---

### Phase 2 — Citation verification (trust; app-side, deterministic)
**Targets D1.** The single highest-trust-per-line fix (council unanimous).

**Ships:** at rec compose and at deep-result write-back, assert each quoted span is a normalized substring of the chunk it cites; set `citation_verified` bool + `citation_mismatch_reason`; surface the flag in the app.
**Acceptance:** a deliberately corrupted citation is flagged; clean ones pass.
**Gate probe:** fuzz cases (OCR run-ons, punctuation-free transcript); zero false-clean on planted bad cites.

---

### Phase 3 — Contradiction / staleness pass (Claude-Code-side; targets A6)
**Stops conflicting sources from averaging into nothing.**

**Ships:** `/rx-contradiction-check` command — takes the deep candidate set (or a rec's sources), uses session judgment (no API) to label pairwise stance (agree | contradict | orthogonal) + staleness vs query horizon, POSTs a contradiction report to `/v1/rx/deep`; app shows a "⚠ sources conflict" banner.
**Acceptance:** planted contradictory pair → flagged; agreeing pair → not.
**Gate probe:** precision on a small hand-labeled set (guard against alarm fatigue from false conflicts); verify NO API key used.

---

### Phase 4 — Feedback-loop de-biasing (app-side; targets B4, B3, D2)
**The most dangerous compound: the self-influence flywheel that reads as learning.**

**Ships:**
- **Attribution split:** `rec_influence_kind` on the trade↔rec link — `preceded_independent` vs `influenced`. `predictive_lift` in `/rx-analyze` **excludes** `influenced` trades.
- **Explicit hypothesis linkage** replacing the false-positive-prone substring match (D2): linkage named at compose/disposition time; substring kept only as a fallback *suggestion*. Also defuses the D2 landmine.
- **P&L value metric:** realized-P&L-per-rec surfaced alongside action_rate; health view shows engagement-vs-value divergence (e.g. GREEN-engagement / RED-P&L).

**Acceptance:** influenced trades excluded from lift; explicit linkage populated; P&L computed where trades exist.
**Gate probe:** lift number changes when an influenced trade is reclassified; the planted "NVDA bearish chunk vs bullish hypothesis" no longer silently mislinks; disposition flow unregressed.

---

### Phase 5 — External disconfirmation (Claude-Code-side; targets B2)
**Breaks the same-vault counter-thesis bubble for finance.**

**Ships:** `/rx-counter-external` — for a finance rec, pull ≥1 disconfirming source from OUTSIDE the vault (WebSearch/WebFetch, subscription), summarize the strongest external counter-argument, POST to `/v1/rx/deep`; app shows "external counter" beside the vault counter-thesis.
**Acceptance:** produces a genuinely external, on-topic counter for a sample rec.
**Gate probe:** spot-check counter is external + relevant; **document the NEW bias vector** (web-surface bias replaces filter-bubble bias — net positive, not bias-free); verify NO API key.

---

### Phase 6 — Drift/monitoring + n=1 landmine ledger (app-side + docs; Tier 3)
**Ships:**
- **Preference-drift detector** (distinct from the existing prediction-MAPE drift): track action_rate + subjective_fit *slope* over rolling windows; alert on slope breach, not just absolute band (B6).
- **Embedding-distribution-shift monitor:** track per-domain incoming-chunk embedding centroid/variance over time; periodic, cheap; alert on significant shift.
- **Landmine ledger:** explicit tech-debt entries with TRIGGER conditions — "D2 substring fallback → remove at 2nd user," "E2 single operator UUID → re-architect auth at multi-user," etc.

**Acceptance:** preference-drift fires on a synthetic declining series; shift monitor fires on injected drift; ledger entries written with triggers.
**Gate probe:** detector unit tests on synthetic series; thresholds documented + justified.

---

### Phase 7 — Port to other domains + repopulate tables + retro
**Ships:**
- Port deep mode, citation verification, contradiction pass, drift detectors to fitness/learning/nutrition (registry-driven via `_domains.yaml` where possible).
- **Repopulate the limitations tables** (Themes A–E + interaction effects) marking each row FIXED / MITIGATED / UNCHANGED / NEW, with the mechanism that moved it.
- **Retro:** before/after recall + quality deltas vs the Phase-0 baseline; residual risks; **risks introduced by the fixes** (web-surface bias, deep-mode compute cost, contradiction-pass precision ceiling, explicit-linkage mislabeling); trade-offs actually taken.

**Acceptance:** other domains run the new paths; tables repopulated; retro written.
**Gate probe:** full pytest; recall/quality deltas quantified; retro reviewed.

---

## Dependency graph

```
Phase 0 (log + endpoint + baseline)
   ├──> Phase 1 (deep retrieval) ──> Phase 3 (contradiction, uses deep set)
   │                                      └──> Phase 5 (external counter)
   ├──> Phase 2 (citation verify)
   ├──> Phase 4 (attribution + P&L)
   └──> Phase 6 (drift + ledger)
Phases 1–6 ──> Phase 7 (port + repopulate tables + retro)
```

---

## Trade-offs flagged (explicit)

1. **Deep retrieval completeness vs always-on.** Deep mode is expensive → on-demand in Claude Code, not automatic in the app. Insights become operator-triggered, not ambient. (Accepted: this is the whole point of the cost seam.)
2. **Contradiction/disconfirmation precision ceiling.** LLM stance-labeling will mislabel some pairs; false "conflict" flags risk alarm fatigue. Mitigated by a precision gate, not eliminated.
3. **External disconfirmation introduces web-surface bias** — replaces the filter bubble with whatever the web ranks highly. Net positive, still a bias.
4. **Explicit hypothesis linkage** shifts burden to compose-time naming; mislabels become a *new* (but auditable) error mode, vs silent substring mislinks.
5. **Retrieval-log storage growth** on the laptop — bounded by a retention policy added in Phase 0.

---

## What the final retro will compare

The Themes A–E limitation tables + the interaction-effects table, re-scored per use-case (FIN/FIT-NUT/LRN), plus a new "risks introduced by the fixes" section and the trade-offs actually taken.
