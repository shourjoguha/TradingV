# Cross-Door Retrieval-Depth & De-biasing Porting Program

**Status:** PLAN (not yet executing)
**Authored:** 2026-06-13
**Parent:** ports the finance work in [retrieval-depth-and-debiasing-program.md](retrieval-depth-and-debiasing-program.md) (+ [RETRO](retrieval-depth-RETRO.md), [gates](GATES-retrieval-depth.md)) to the other three doors.
**Operator decisions (confirmed):** fitness/nutrition enrichment → **Supabase table + Lovable UI**; **all three doors** in scope now.

---

## The porting principle (what's free vs what's per-door)

The finance program was built so the expensive, reusable parts are **domain-agnostic** and the only door-specific part is the **write-back + surfacing** (because each door uses a different store under the rx routing lock).

| Layer | Portability |
|---|---|
| `deep_search` + `/deep_search` endpoint + `retrieval_log` (vault indexer) | **Free** — already per-domain; each door's indexer runs on its own port (fitness :8002, nutrition :8003, learning :8004). Zero code change. |
| Pure modules: `citation_check`, `drift_monitor`, `deep_governors` | **Free** — domain-blind, callable from any door's command. |
| `analytics` (action_rate, drift, value) | **Partial** — action_rate + preference-drift port free; the **value metric** does NOT (finance = realized P&L; other doors have no P&L → need a door-appropriate value signal). |
| The 3 Claude-Code commands | **Parametrize** — add a door/port arg + per-door write-back target. |
| Write-back store + UI surface | **Per-door build** — finance=TradingV postgres (done); fitness/nutrition=Supabase+Lovable (cross-repo); learning=markdown sidecar. |

### Capability × door matrix

| Capability | Lakshmi (finance) | Zeus (fitness) | Athena (nutrition) | Ganesh (learning) |
|---|---|---|---|---|
| Deep retrieval (filter-late) | ✅ done | port (corpus-rich) | port (dormant) | port (thin — empty corpus) |
| Citation verification | ✅ done | port | port (dormant) | port |
| Contradiction + severity governor | ✅ done | port | port (dormant) | port |
| External disconfirmation + credibility governor | ✅ done | port (research vs protocol) | port (dormant) | optional |
| Preference + embedding drift monitors | ✅ done | port | port (dormant) | port |
| Attribution split (B4) | ✅ P&L-based | **N/A → value-proxy** | N/A | N/A |
| Value-vs-engagement (B3) | ✅ P&L | **drift-improvement / goal-progress** | goal-progress | sprint/goal-progress |

**Door stores + maturity (rx routing lock — NEVER cross-write):**
- **Lakshmi / finance** — TradingV postgres · `/rx-finance` panel · live · **done**.
- **Zeus / fitness** — Supabase (verocity DB) · Lovable app · live + mature · indexer :8002.
- **Athena / nutrition** — Supabase (planned, unused) · no UI (D-047) · **scaffold, no generator** · indexer :8003.
- **Ganesh / learning** — markdown only · editor, no UI · live but **empty corpus** · indexer :8004.

---

## Hard invariants (extend the finance program's)

1. **Routing lock is absolute.** finance rec/enrichment data NEVER touches Supabase; learning NEVER touches Lovable/Supabase; fitness+nutrition enrichment lives in Supabase only. Every write path filters `domain IN (...)` for its store.
2. `ANTHROPIC_API_KEY` stays unset; deep work runs on-demand from Claude Code (subscription). Deep_search is pure-Python local.
3. Per-store single write path: TradingV via `/v1/rx/deep`; Supabase via the verocity ingest path; learning via the markdown writer. No direct cross-store writes.
4. The always-on surfaces stay cheap; heavy work is operator-triggered.

## Gated-pass protocol

Identical to the finance program: build → gap/bug sweep (tests + planted-failure probe + regression) → self-correct → forward re-eval → `PASS`/`PASS-WITH-FIXES`/`BLOCKED` to `GATES-cross-door.md`. Advance only on PASS; BLOCKED stops for the operator.

---

## Phases

### Phase P0 — Shared core: parametrize + value-metric + Supabase store
**Goal:** make the reusable core door-aware before touching any single door.

**Ships:**
- **Command parametrization**: `/rx-deep-retrieve`, `/rx-contradiction-check`, `/rx-counter-external` take a `door` arg → resolve indexer port (8001–8004) + write-back target (TradingV | Supabase | markdown). Finance behavior unchanged when door omitted/finance.
- **Door-appropriate value metric** in `analytics.py`: generalize `value_vs_engagement` so the "value" signal is pluggable — finance=realized P&L (existing); fitness/nutrition/learning = **drift-composite improvement over the rec's horizon** and/or **goal-progress delta** (Zeus `goals.yaml`, Ganesh `learning_goals.md`). Pure functions + tests.
- **Supabase `rx_deep_results` table** in the verocity DB (migration via Supabase MCP): mirrors the TradingV shape (`rec_id`/`query_hash`, `kind`, `payload` JSONB, `domain` CHECK IN ('fitness','nutrition'), `created_at`). RLS consistent with the verocity `recommendations` table.

**Acceptance:** commands route by door; value-metric helper returns sensible deltas on synthetic data; Supabase table created + round-trips a payload; finance path unaffected.
**Gate probe:** finance regression (existing 942 tests green); Supabase CHECK rejects `domain='finance'`.

### Phase P1 — Zeus / fitness end-to-end
**Goal:** full capability set on the most mature non-finance door.

**Ships:**
- Deep retrieval against :8002; citation verification on fitness rec source_refs; contradiction + severity governor; external disconfirmation + credibility governor (research papers vs the operator's protocol); preference + embedding drift monitors over fitness dispositions.
- **Attribution/value (B3/B4 analog)**: no P&L → value = did the rec move the fitness drift composite favorably / advance a Zeus goal. Define the fitness "creditable outcome" (e.g. adherence + drift-improvement post-rec) and the influence split (rec preceded vs caused the training change).
- **Write-back → Supabase** `rx_deep_results` (domain='fitness'); **Lovable UI surface** (cross-repo: verocity app shows deep set, conflict banner gated by governor, external counter w/ governed credibility).

**Acceptance:** each capability produces + surfaces a fitness result in Lovable; governors gate banners/credibility identically to finance.
**Gate probe:** planted fitness cases (recall save vs fast path; fabricated citation flagged; weak single-source counter capped); Lovable renders governed flags.

### Phase P2 — Ganesh / learning end-to-end (markdown)
**Goal:** same capabilities, markdown-only store, empty-corpus-safe.

**Ships:**
- Deep retrieval against :8004; citation/contradiction/drift; value = sprint/goal progress (`active_sprints.md`, `learning_goals.md`).
- **Write-back → markdown sidecar** (`Ganesh/rx/deep/<rec>.md` or frontmatter blocks); editor reads. No DB, no endpoint.
- **Empty-corpus handling**: deep retrieval returns little until corpus filled — surface "thin corpus" honestly (the `retrieval_log` already makes zero-surfaced visible), never fabricate.

**Acceptance:** capabilities write valid markdown the editor renders; thin-corpus path degrades honestly.
**Gate probe:** empty-corpus query → explicit "no/low results" not a hallucinated set; citation verify works on learning vault quotes.

### Phase P3 — Athena / nutrition wiring (dormant-safe)
**Goal:** wire the Supabase write-back + commands so nutrition is ready the moment its generator (Phase J.2) exists — without a live generator to exercise.

**Ships:**
- Command routing for door=nutrition → :8003 + Supabase (`domain='nutrition'`).
- Reuse the P0 Supabase table (already allows nutrition).
- **Wiring tests + a J.2 trigger note** (landmine-ledger style): the path is built but unexercised until a nutrition generator emits recs. Guard against bit-rot with a smoke test that posts a synthetic nutrition deep-result + reads it back.

**Acceptance:** synthetic nutrition deep-result round-trips through Supabase; no live-generator dependency.
**Gate probe:** routing picks :8003 + Supabase; CHECK accepts nutrition, rejects finance.

### Phase P4 — Cross-door retro + per-door capability matrix
**Ships:** repopulate the capability × door matrix with FIXED/MITIGATED/UNCHANGED/N-A per door; document the value-metric divergence (P&L vs drift-improvement vs goal-progress); residual + newly-introduced risks per door; the cross-repo (Lovable) maintenance surface added.

---

## Dependency graph

```
P0 (parametrize + value-metric + Supabase table)
 ├──> P1 Zeus/fitness   (Supabase + Lovable)
 ├──> P3 Athena/nutrition (Supabase, dormant)   [reuses P0 table]
 └──> P2 Ganesh/learning (markdown)
P1–P3 ──> P4 (cross-door retro + matrix)
```

---

## Trade-offs flagged (decide / accept before each phase)

1. **Cross-repo surface (P1/P3).** Choosing Supabase+Lovable (operator decision) means the fitness/nutrition surfaces touch the **separate verocity/Lovable codebase** — bigger blast radius than finance (all in-repo). The deep-result *generation* stays here (Claude Code); the *table + UI* live in verocity. Plan budgets a verocity-side migration + Lovable component per surface.
2. **Value-metric divergence (P1/P2/P3).** No P&L outside finance → value = drift-improvement / goal-progress, which are **softer, laggier signals** than realized money. B3 divergence detection is therefore weaker on non-finance doors; the engagement-vs-value flag is directional, not dollar-precise. Accept, and label it.
3. **Nutrition dormancy (P3).** Wiring an unexercised path risks bit-rot. Mitigated by a synthetic round-trip smoke test + an explicit J.2 trigger, but the path won't see real recs until the generator exists — so its real-world correctness is unverified until then.
4. **Learning empty corpus (P2).** Deep retrieval + citation are thin until the operator fills `Videos/learning/`. The capabilities are correct but low-yield until content lands.
5. **Routing-lock blast radius.** Three stores + two repos multiplies the "never cross-write" surface. Every write path needs its own domain filter + test; a single mis-routed write violates D-045/D-047.

---

## What carries over for free (no rebuild)

`deep_search`, `/deep_search`, `retrieval_log`, `citation_check`, `drift_monitor`, `deep_governors`, and `analytics.action_rate`/`preference_drift` are all already domain-agnostic (verified Phase 7). Porting consumes them; it does not re-implement them. The genuinely new work is: command parametrization, the per-door value metric, and the two non-TradingV write-back/surfacing paths (Supabase+Lovable, markdown).
