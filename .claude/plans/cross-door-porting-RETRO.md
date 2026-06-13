# Cross-Door Porting — Retro & Capability Matrix

**Completed:** 2026-06-13 · P0–P4 PASS · TradingView suite **946 green** · verocity `astro check` 0 errors / **78 vitest green**.
**Companion:** [plan](cross-door-retrieval-depth-porting.md) · [gates](GATES-cross-door.md) · parent [finance program](retrieval-depth-and-debiasing-program.md).

The retrieval-depth + de-biasing capabilities, built finance-first, are now ported across all four doors — store-aware, respecting the rx routing lock (no cross-writing).

## Capability × door — final status

| Capability | Lakshmi (finance) | Zeus (fitness) | Athena (nutrition) | Ganesh (learning) |
|---|---|---|---|---|
| Deep retrieval (filter-late) | ✅ live (:8001, TradingV) | ✅ wired (:8002, Supabase) | 🟡 wired-dormant (:8003) | 🟡 wired, empty corpus (:8004) |
| Citation verification | ✅ live | ✅ available (pure, domain-blind) | 🟡 dormant | ✅ available |
| Contradiction + severity governor | ✅ live | ✅ wired + UI banner (governor-gated) | 🟡 dormant | ✅ available (markdown) |
| External counter + credibility governor | ✅ live | ✅ wired + UI (governed credibility) | 🟡 dormant | ⬜ optional |
| Preference + embedding drift | ✅ live | ✅ available (pure) | 🟡 dormant | ✅ available |
| Value-vs-engagement (B3) | ✅ P&L | ✅ drift-improvement (pluggable) | 🟡 drift-improvement (dormant) | ✅ goal/sprint-progress |
| Attribution split (B4) | ✅ trade influence | 🟡 value-proxy (not data-wired) | N/A | N/A |
| **Write-back store** | TradingV postgres `/v1/rx/deep` | **Supabase `rx_deep_results`** | Supabase (same table) | **markdown sidecar** |
| **UI surface** | TradingV `/rx-finance` panel | **Lovable Coach modal** (`DeepEnrichment`) | none (D-047) | editor (markdown) |

✅ live/built · 🟡 wired but dormant/unexercised · ⬜ optional/skipped · N/A not applicable.

## What was actually built (vs ported free)

- **Ported free (zero change):** `deep_search`, `/deep_search`, `retrieval_log`, and the pure modules `citation_check`, `drift_monitor`, `deep_governors`, `analytics.action_rate`/`preference_drift` — all domain-agnostic, verified Phase 7.
- **P0 new:** command `--door` routing (port + write-back target); pluggable value metric (`engagement_vs_value` + `drift_improvement_per_rec`); Supabase `rx_deep_results` table with a routing-lock CHECK *stronger than the base recommendations table*.
- **P1 new:** the Claude-Code→Supabase write path (round-trip proven live) + the Lovable `DeepEnrichment` UI (type + query + component + Coach-modal wiring), governor verdicts carried through to the banner/credibility display.
- **P2/P3:** markdown sidecar (learning) + nutrition Supabase wiring — both on top of P0, smoke-tested, dormant where the generator/corpus doesn't exist yet.

## Risks the porting introduced

- **🆕 Cross-repo maintenance surface.** Fitness/nutrition UI now lives in the *separate* verocity/Lovable repo (`feat/rx-deep-enrichment` branch). The deep-result *generation* (Claude Code) and *display* (verocity) must stay in sync on the payload shape + governor contract. A payload-shape change now touches two repos.
- **🆕 Two identity spaces.** Supabase `owner_user_id` (verocity auth uid) ≠ TradingV `RX_OPERATOR_UUID`. The fitness write path inherits owner from the rec; a wrong-uuid write would be invisible to the operator's RLS-scoped reads. Documented in the command.
- **🆕 Three stores, one contract.** TradingV postgres + Supabase + markdown each carry `rx_deep_results`-shaped payloads. The routing-lock CHECK (`domain IN ('fitness','nutrition')` on Supabase) structurally blocks finance leakage, but each new write path needs its own domain guard + test.

## Honest residual (operator-side)

- **Push pending:** verocity `feat/rx-deep-enrichment` branch is committed, NOT pushed — pushing auto-deploys the live fitness app via Lovable (operator's call).
- **No live browser walkthrough** of the Coach modal (needs auth + seeded rows); rests on clean typecheck + green vitest + proven Supabase round-trip + Python-side governor unit tests.
- **Fitness B4 value not data-wired:** the pluggable value metric exists but assembling real before/after fitness drift snapshots per rec is unbuilt.
- **Nutrition dormant** until Phase J.2 generator; **learning low-yield** until corpus filled.
- **Value-metric divergence accepted:** no P&L outside finance → drift-improvement / goal-progress are softer, laggier signals; B3 divergence detection is directional, not dollar-precise, on non-finance doors.

## Trade-offs taken

1. **Supabase + Lovable** for fitness/nutrition (operator decision) over a lightweight markdown sidecar — full in-app visibility at the cost of cross-repo surface.
2. **All-three-doors now** over Zeus-first — nutrition wired though it can't be exercised (J.2 trigger), accepting bit-rot risk for "ready when the generator lands."
3. **Pure modules reused, not re-implemented** per door — one source of truth for citation/governor/drift logic across all stores.
4. **Routing lock enforced at the DB** (Supabase CHECK) — finance can never leak into the fitness store, structurally.
