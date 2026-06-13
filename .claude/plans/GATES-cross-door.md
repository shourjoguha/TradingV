# Gate verdicts — Cross-Door Retrieval-Depth Porting

Gate protocol per [cross-door-retrieval-depth-porting.md](cross-door-retrieval-depth-porting.md). One entry per phase.

---

## Porting P0 — Shared core: parametrize + value-metric + Supabase table — **PASS** (2026-06-13)

### Shipped
- **Command door-routing**: `/rx-deep-retrieve`, `/rx-contradiction-check`, `/rx-counter-external` all take `--door finance|fitness|nutrition|learning` (default finance) → resolve indexer port (8001–8004) + write-back target (TradingV `/v1/rx/deep` | Supabase `rx_deep_results` | markdown sidecar). Routing table + "never cross-write" rule documented in each. Finance behavior unchanged when door omitted.
- **Pluggable value metric** (`app/rx/analytics.py`): new `engagement_vs_value(dispositions, value_per_rec, value_label)` generic core; `value_vs_engagement(dispositions, trades)` refactored to delegate (finance back-compat keys preserved); `drift_improvement_per_rec(rows)` = the non-finance value signal (drift_before − drift_after, positive = rec helped). Value is now door-pluggable: P&L (finance) | drift-improvement (fitness/nutrition) | goal-progress (learning).
- **Supabase `rx_deep_results` table** in verocity (`zwuaieavvmjacqtbzowm`): mirrors the TradingV shape (rec_id/query_hash/kind/payload jsonb/created_at) + `owner_user_id`, with **a stronger routing-lock guard than the base table** — `domain CHECK IN ('fitness','nutrition')` makes a finance write structurally impossible. RLS mirrors `recommendations` (owner-scoped authenticated insert/select/update + anon showcase select). Migration `rx_deep_results_cross_door_porting`.

### Gap/bug sweep
- Full app suite: **946 passed, 0 failed** (+4 analytics tests).
- Value metric: generic divergence flags green-engagement/negative-value; finance wrapper keeps `total_realized_pnl_on_recs`/`recs_with_pnl` keys (no caller breakage); drift_improvement aggregates per rec, skips incomplete rows.
- Supabase: table has the 8 expected columns; **routing-lock CHECK verified live** — a `domain='finance'` insert is rejected by `ck_rx_deep_results_domain`; `domain='fitness'` accepted (test row inserted + deleted). RLS enabled.

### Known limitations / honest caveats
- **Base `recommendations` table in verocity has no `domain` column** (this Supabase implicitly holds fitness/nutrition). The new `rx_deep_results.domain` is therefore the *first* explicit domain guard in that DB — stronger than the base table, which is good, but means fitness-vs-nutrition separation in `recommendations` itself is still implicit (out of scope here).
- **Write auth from Claude Code to Supabase not yet wired** — the table + RLS exist; the actual write path (service-role key or operator auth from the `/rx-*` commands) is P1 work. RLS protects Lovable reads; the command write path is built in P1.
- Value metric is pure; assembling `value_per_rec` from real drift snapshots (before/after the rec horizon) is per-door integration in P1/P2.

### Forward re-evaluation (P1)
- P1 (Zeus/fitness) now has: door-routed commands, the Supabase target table, and the drift-improvement value metric. Remaining P1 work is genuinely the **cross-repo surface**: the Claude-Code→Supabase write path + the Lovable UI components (deep set, governor-gated conflict banner, governed external counter). **P1 requires verocity/Lovable repo access** — flagged for the operator before starting.
- No plan change.

### Verdict: **PASS** → P1 (requires verocity/Lovable repo access to proceed).

---

## Porting P1 — Zeus/fitness end-to-end (Supabase + Lovable) — **PASS** (2026-06-13)

Operator provided the repo: `github.com/shourjoguha/verocity-Multi` (Astro + React 19 + Supabase + Tailwind), cloned to `~/Documents/Claude/verocity-Multi`.

### Shipped
- **Supabase write path** (Claude-Code → `rx_deep_results`): documented in `/rx-deep-retrieve` non-finance write-back — insert via Supabase MCP, `owner_user_id` **inherited from the rec** (distinct identity space from the TradingV operator uuid), `domain` CHECK-guarded. **Live round-trip proven**: inserted a governed contradiction enrichment tied to a real fitness rec → read back (`severity=high, raise_banner=true`) → deleted.
- **Lovable UI (verocity repo, branch `feat/rx-deep-enrichment`)**:
  - `RxDeepResult` type + `getDeepResults(recId)` query (owner-scoped by RLS, mirrors recommendations).
  - `DeepEnrichment.tsx` rendered in the Coach rec-detail modal: deep-retrieval set (hop badges + judgment notes); **contradiction banner shown ONLY when `governor.raise_banner`** (alarm-fatigue guard carried through to the UI); **external counter labelled with `governor.credibility`** + muted/"weak" when it doesn't count (web-surface-bias guard). Defensive against LLM-authored payload shapes.
- Commands already door-routed (P0).

### Gap/bug sweep
- verocity `astro check`: **0 errors, 0 warnings** (3 pre-existing hints in unrelated files). vitest: **78 passed**.
- TradingView app untouched by P1 (commands are markdown; P0 analytics already verified at 946).
- Supabase: write→read→delete round-trip succeeded against the live table; routing-lock CHECK confirmed in P0.
- Committed to a **branch, not pushed** — pushing auto-deploys the live fitness app via Lovable, which is the operator's call.

### Known limitations / honest caveats
- **No live browser walkthrough.** Rendering the Coach modal with a seeded deep-result requires an authenticated verocity session + seeded rows — not done here. Verification rests on: clean typecheck, green vitest, the proven Supabase round-trip, and the governor logic being unit-tested on the Python side. A logged-in click-through is operator-side.
- **Fitness value/attribution (B3/B4 analog) not wired to real data.** The pluggable `drift_improvement_per_rec` exists (P0) but assembling real before/after fitness drift snapshots per rec is unbuilt — the value metric is available, not yet populated for fitness.
- **Push pending operator.** The branch must be reviewed + pushed by the operator to reach the live Lovable app.

### Forward re-evaluation (P2/P3)
- P2 (learning, markdown) needs no repo access — markdown sidecar write + the same commands. P3 (nutrition) reuses the P0 Supabase table + this same write path, dormant until a nutrition generator exists.
- No plan change.

### Verdict: **PASS** → P2 (learning).

---

## Porting P2 — Ganesh/learning (markdown) — **PASS** (2026-06-13)

### Shipped
- Learning is covered by P0's command door-routing (→ indexer :8004 + **markdown sidecar** write-back `Ganesh/rx/deep/<rec_id>.md`, payload as frontmatter + readable body; editor surfaces it; no DB).
- Value signal = goal/sprint-progress via the pluggable `engagement_vs_value` (P0) — `drift_improvement_per_rec` generalizes to any door's drift/progress delta.
- **Empty-corpus safety** is inherent: `deep_search` returns `[]` when no seeds; `retrieval_log` records zero-surfaced honestly; and the command hard-rule "Never fabricate candidates — if the indexer returns nothing, say so" prevents hallucinated results on the empty learning corpus.

### Gap/bug sweep
- No new code (markdown write + existing command routing). No app/test impact.
- Empty-corpus path verified by design: the "never fabricate" rule + retrieval_log zero-surfaced visibility (proven Phase 0/1) cover it.

### Known limitations / honest caveats
- **Unexercised against real content** — the learning vault is empty, so deep retrieval/citation yield little until the operator fills `Videos/learning/`. Capabilities are correct but low-yield today.
- Markdown sidecar has no UI surface beyond the editor (markdown-only door, by routing-lock design).

### Verdict: **PASS** → P3 (nutrition).

---

## Porting P3 — Athena/nutrition (Supabase, dormant-safe) — **PASS** (2026-06-13)

### Shipped
- Command routing for `--door nutrition` → indexer :8003 + Supabase `rx_deep_results` (reuses the P0 table; CHECK already allows nutrition).
- **Dormant-safe smoke test passed**: inserted a `domain='nutrition'` deep_retrieval row keyed by `query_hash` (nutrition has no generator/recs yet) → read back → deleted. Proves the write path works before a nutrition generator exists.

### Gap/bug sweep
- Round-trip verified live against the table; routing-lock CHECK confirmed (P0).
- No app code; reuses P0 infrastructure.

### Known limitations / honest caveats
- **Genuinely dormant**: nutrition is a scaffold (no generator, no recs). The deep path is wired + smoke-tested but **won't see real recs until Phase J.2** ships a nutrition generator. Bit-rot risk mitigated by the smoke test + this explicit trigger note; real-world correctness unverified until J.2.

### Verdict: **PASS** → P4 (retro).

---

## Porting P4 — Cross-door retro + capability matrix — **PASS** (2026-06-13) — PROGRAM COMPLETE

### Shipped
- [`cross-door-porting-RETRO.md`](cross-door-porting-RETRO.md): final capability × door matrix (4 doors), what-built-vs-ported-free, 3 newly-introduced risks (cross-repo surface, two identity spaces, three-stores-one-contract), honest operator-side residual, trade-offs taken.

### Outcome
- All 7 capabilities mapped across 4 doors. finance **live**; fitness **wired + UI built** (Supabase + Lovable branch); nutrition **wired-dormant** (smoke-tested, awaits J.2); learning **wired** (markdown, awaits corpus).
- Pure de-biasing core reused unchanged across all stores; only routing + value-metric + two non-TradingV write paths were new.
- TradingView suite 946 green; verocity 0 typecheck errors / 78 vitest green; Supabase round-trips (fitness + nutrition) proven live; routing-lock CHECK enforced at the DB.

### Verdict: **PASS** — cross-door porting program complete.
