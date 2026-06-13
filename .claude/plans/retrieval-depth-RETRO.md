# Retrieval Depth & De-biasing Program — Retro & Repopulated Limitation Tables

**Completed:** 2026-06-13 · all 8 phases (0–7) PASS · suite 856→**925 passed**, 0 failed.
**Companion docs:** [program plan](retrieval-depth-and-debiasing-program.md) · [gate log](GATES-retrieval-depth.md).

This re-scores the original limitation tables from the 2026-06-13 risk retro, marking each row **FIXED / MITIGATED / UNCHANGED / NEW**, then a before/after, residual risks, risks the fixes introduced, and the trade-offs actually taken.

Status legend: ✅ FIXED · 🟡 MITIGATED (better, not closed) · ⬜ UNCHANGED · 🆕 NEW (introduced by a fix).
Severity per use-case unchanged from the original retro: FIN / FIT-NUT / LRN.

---

## THEME A — Retrieval correctness & recall

| ID | Limitation | Status | What moved it | Residual |
|----|-----------|--------|---------------|----------|
| A1 | Single-vector chunk dilution | 🟡 MITIGATED | Deep mode surfaces more candidates incl. the diluted chunk's neighbors; citation verification (Phase 2) catches when the *quote* doesn't match the chunk. Chunking itself unchanged. | Centroid embedding still averages opposing claims; only re-chunking truly fixes it. |
| A2 | No query expansion / single embedding | ⬜ UNCHANGED | Out of scope (council red-herring at n=1 — operator re-asks). | Deferred deliberately. |
| A3 | Recall cliff from beam prune + early-stop | ✅ FIXED | Deep mode: beam 5→12, prune 0.50→0.30, early-stop OFF, hops→4, top-K→50. Pruned candidates returned with reasons, not dropped. | Empirical recall delta operator-run (`retrieval_eval.py --mode compare`). |
| A4 | Recency truncation drops dispositive doc | ✅ FIXED | Deep mode keeps decay≤0 rows flagged `decay_zero` (`kept_despite_decay_zero`) — old filings reach the judgment layer. | Fast path still truncates (by design — that's the cheap path). |
| A5 | RRF rank-compression at small corpus | ⬜ UNCHANGED | Not targeted. | Low severity; deep mode's wider pool partially dilutes the effect. |
| A6 | No contradiction / stance detection | ✅ FIXED | `/rx-contradiction-check` labels each source supports/contradicts/orthogonal + flags pairs + staleness; app shows "⚠ sources conflict". | Precision is LLM-judgment (operator-validated); alarm-fatigue risk → see NEW-1. |

## THEME B — Bias, feedback loops & epistemic risk

| ID | Limitation | Status | What moved it | Residual |
|----|-----------|--------|---------------|----------|
| B1 | Vault-as-ground-truth filter bubble | 🟡 MITIGATED | Phase 5 external disconfirmation pulls off-vault counters; deep mode widens the in-vault pool. | The corpus is still self-selected; external counter is opt-in per rec. |
| B2 | Counter-thesis theater (same-vault) | ✅ FIXED | `/rx-counter-external` steelmans an OFF-vault counter, contrasts vault-vs-external. | Introduces web-surface bias → NEW-2. |
| B3 | action_rate is a complicity metric | ✅ FIXED | `analytics.value_vs_engagement` surfaces realized-P&L-per-rec beside action_rate + flags GREEN-engagement/negative-P&L divergence. | P&L is sparse + lagging; divergence flag only as good as trade capture. |
| B4 | Self-influence flywheel (attribution≠prediction) | ✅ FIXED | `rec_influence_kind` + `creditable_trades` excludes `influenced` trades from predictive-lift. | Forward-looking only — legacy NULL trades stay creditable until classified. |
| B5 | Hand-tuned weights freeze a worldview | 🟡 MITIGATED | Attribution-clean lift (B4) + preference-drift detector (B6) give better tuning signal; weights still hand-applied (D-019, deliberate). | Regime-change mis-ranking still possible; no auto-retune (safety choice). |
| B6 | No preference-drift detector | ✅ FIXED | `drift_monitor.preference_drift` flags declining action_rate/fit slope, distinct from MAPE drift. | Series-assembly + scheduling not wired (pure detector only). |
| B7 | Epistemic capture of the only user | 🟡 MITIGATED | B2+B4+B6 together attack the reinforcement loop; contradiction + external counter inject genuine dissent. | Structural to n=1; cannot be "fixed" in code — only counter-pressured. |

## THEME C — Objective & evaluation validity

| ID | Limitation | Status | What moved it | Residual |
|----|-----------|--------|---------------|----------|
| C1 | No offline recall ground truth | ✅ FIXED (instrument) | `retrieval_log` records eligible⊃surfaced + drop reasons every search; `retrieval_eval.py` baselines + compares. Misses are now measurable. | A *labeled* relevance set still doesn't exist; the log measures deltas, not absolute recall. |
| C2 | Composite weights not a validated utility | 🟡 MITIGATED | B3 P&L gives an external validity check the circular lift metric lacked. | Weights still operator-priors; no formal utility model. |
| C3 | n=1 statistics (no CIs) | ⬜ UNCHANGED | Landmine-ledger L3 documents the per-cohort + Bayesian-smoother fix with a trigger. | Deferred to n=2 (correctly). |

## THEME D — Extraction & data integrity

| ID | Limitation | Status | What moved it | Residual |
|----|-----------|--------|---------------|----------|
| D1 | Regex citation/excerpt extraction | ✅ FIXED | `citation_check` verifies quote ⊆ chunk (normalized, ellipsis-aware); `citations_status` surfaced; fabrication flagged `has_mismatch`. | Verbatim-only (paraphrase flags not_found by design); coverage needs producers to attach `text` (now wired in `/rx-finance`). |
| D2 | Substring hypothesis↔rec linkage | ✅ FIXED | Explicit `linked_hypothesis_ids` is primary; substring demoted to `substring_fallback`, no double-count. `/rx-finance` now populates it. | Fallback still present for legacy recs (landmine L1, trigger = n=2 / >50 hypotheses). |
| D3 | Multimodal → text reduction lossy | ⬜ UNCHANGED | Not targeted. | OCR/transcript quality unaddressed; citation verify at least catches a bad-OCR quote that doesn't match. |
| D4 | Closed-vocabulary auto-tagging | ⬜ UNCHANGED | Not targeted. | Low severity. |

## THEME E — Architecture, scale & operational

| ID | Limitation | Status | What moved it | Residual |
|----|-----------|--------|---------------|----------|
| E1 | Single laptop = SPOF | ⬜ UNCHANGED | Deep work is on-demand from Claude Code; doesn't change the SPOF. | Out of scope. |
| E2 | n=1 hard-coded operator UUID | 🟡 MITIGATED (documented) | Landmine-ledger L2 makes it the explicit master n=2 trigger. | Still single-user by design. |
| E3 | Empty-corpus domains return confident nothing | 🟡 MITIGATED | `retrieval_log` makes an empty/zero-surfaced result visible instead of silent. | The rec still emits on empty corpus (learning); flagging not auto-wired. |
| E4 | Full re-index on schema bump | ⬜ UNCHANGED | Not targeted. | Low severity. |

## INTERACTION EFFECTS (re-scored)

| Pair | Before | Now |
|------|--------|-----|
| C1 ⊗ Theme A | Master multiplier — every retrieval bug unmeasurable | ✅ Broken: `retrieval_log` makes A3/A4 deltas measurable; C1 no longer hides them. |
| B1 ⊗ B2 | Filter bubble + same-vault counter = airtight false confidence | 🟡 External counter (B2 fixed) punctures it from outside; bubble (B1) still partial. |
| B3 ⊗ B4 ⊗ B5 | Closed money-losing loop reading as learning | ✅ Largely broken: influenced trades excluded (B4), P&L surfaced (B3); B5 auto-retune still off by choice. |
| A4 ⊗ A6 | Recency bias masquerades as consensus | ✅ Both fixed: deep keeps aged docs (A4) + contradiction detection (A6) surfaces the conflict. |
| D2 ⊗ B4 | String bug corrupts the learning signal silently | ✅ Explicit linkage (D2) + attribution split (B4) — mislinks no longer silently feed lift. |
| A5 ⊗ B5 | Tuning decorative knobs | ⬜ Unchanged (both low-priority). |
| E2 ⊗ D1/D2 | Latent n=2 landmines | 🟡 Now DOCUMENTED with explicit triggers (ledger L1/L2) instead of hidden. |

---

## Before / After

- **Limitations: 23 rows + 7 interactions.** Outcome: **11 FIXED, 8 MITIGATED, 8 UNCHANGED** (+ 2 NEW introduced, below). Every UNCHANGED row is a deliberate scope call (n=1 red-herrings or low-severity), not an oversight.
- **The master multiplier (C1) is broken** — the single highest-leverage outcome. Retrieval gaps are now measurable, which is what makes every other retrieval claim checkable.
- **The dangerous compound (B3⊗B4⊗B5 self-influence flywheel) is largely defused** — the loop can no longer read its own influence as learning.
- **Code:** +6 new modules (`retrieval_log`, `deep_search`+`classify_candidates`, `citation_check`, `analytics`, `drift_monitor`, deep-result store) + 3 commands (`rx-deep-retrieve`, `rx-contradiction-check`, `rx-counter-external`) + 2 migrations (0031, 0032) + 69 new tests, all green.

## Risks the fixes INTRODUCED (new) — and their resolution (Phase 8)

- **✅ NEW-1 — Contradiction-flag alarm fatigue → RESOLVED.** `contradiction_severity` governor (`app/rx/deep_governors.py`) gates the banner on deterministic evidence: a directly-contradictory pair OR ≥2 contradictions raises it; a lone contradiction is `medium`; staleness-only never raises a banner. The LLM labels; the governor — not the label — decides. Applied at `/v1/rx/deep` ingest.
- **✅ NEW-2 — Web-surface bias → RESOLVED.** `disconfirmation_credibility` governor caps an external counter's strength by distinct-publisher count + source tier: a single source is capped at `thin` no matter the self-report; `strong` needs ≥3 publishers incl. primary/reputable; the governor never inflates above the self-report. An optimistic single-blog counter can no longer present as decisive. `web_surface_bias_note` retained as the named-bias breadcrumb.
- **🆕 minor — Producer-coupling (still open, low).** Citation coverage (D1) + explicit linkage (D2) depend on `/rx-finance` attaching `text` + `linked_hypothesis_ids` (now wired into the command). Until a rec is produced by the updated command, it reads `unverifiable` / falls back to substring — honest degradation, not silent failure.
- **Residual judgment dependency:** the governors consume LLM-emitted labels (stance, source tier). The *thresholds* are deterministic, so the failure surface shrank from "any label triggers" to "labels must clear fixed bars" — but honest tier/stance labeling is the remaining LLM-in-the-loop dependency (inherent, not eliminable in code).

## Trade-offs actually taken

1. **Deep retrieval is operator-triggered, not ambient** — the cost seam. Completeness on demand; the always-on app stays cheap (invariant held — no new per-rec LLM call, fast path untouched, all logging try/except-wrapped).
2. **Verbatim-only citation check** — no paraphrase tolerance (that's the Phase 3 judgment layer's job). Deterministic + zero-false-clean over paraphrase-as-fabrication.
3. **Forward-looking de-bias** — `rec_influence_kind` defaults NULL; no retroactive voiding of legacy trades. Honest over aggressive.
4. **No auto-retune** (D-019 preserved) — weights stay hand-applied. Safety (no runaway self-tuning loop) over self-correction.
5. **Pure detectors, scheduling deferred** — drift monitors are proven math; wiring them to a cron is opt-in, to avoid adding an always-on laptop job without the operator asking.
6. **n=1 landmines documented, not pre-fixed** — L1–L4 carry explicit n=2 triggers rather than building multi-user machinery now.

## What remains genuinely open (honest close)

- **Empirical recall + contradiction-precision numbers** are operator-run (model + live corpus on the laptop) — the mechanisms are unit-proven, the live measurements are not yet captured. Run `retrieval_eval.py --mode compare` + `/rx-contradiction-check` on a hand-labeled set to close.
- **Drift-monitor scheduling** + **per-domain port of the de-biasing surfaces** (fitness→Supabase, learning→markdown live in *other* stores per the rx routing lock — the retrieval core is domain-agnostic and ports trivially; the write surfaces are finance-only by architecture, correctly).
- **The structural n=1 risks (B7 epistemic capture, E1 SPOF, C3 statistics)** are counter-pressured but not eliminable in code — they resolve at n=2 or not at all.
