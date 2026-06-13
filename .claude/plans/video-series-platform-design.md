# Video Series — Platform Design (build-in-public)

**Status**: brainstorm / pre-plan (north star, authored before execution)
**Date**: 2026-05-25
**Branch**: `claude/video-series-platform-design-Cdf3R`

> Design + rationale for an educational short-form video series about TradingV.
> Operator-confirmed framing (2026-05-25): **goal = build-in-public**;
> **deliverable = all four** (content architecture, in-platform feature, real
> production, plan + pilot); **forks = design-for-forkability, don't commit
> specific forks yet**; **formats = Reels + Shorts + TikTok (vertical short)
> + longer YouTube explainers**.

---

## TL;DR (the north star)

A build-in-public series where **every episode is one real decision we shipped**,
told with a receipt. The platform is uniquely suited to this because it already
generates falsifiable claims with evidence — ADRs (what we chose *not* to build),
roadmap retros (what actually happened vs. the plan, with test counts and
latency numbers), and a live signal layer (predictions graded after the fact).

The content architecture is **hierarchical and forkable on purpose**, mirroring
the platform's own information architecture: atomic chunk → channel rollup →
domain. An episode is the atomic unit; arcs and series are the rollups; the
domain (Trading) can fork into siblings the same way the knowledge vault forked
finance → fitness → nutrition (same code, different scope).

---

## 1. Goals & non-goals

### Goals
- **Build trust through transparency.** Build-in-public's currency is honest
  reasoning, not polish. We have an unfair advantage: a repo full of *documented*
  decisions and *measured* outcomes.
- **A format that scales without burning the operator.** One reusable episode
  template + a hook library + a backlog that's *already written* (every ADR and
  retro is a candidate episode). Production becomes assembly, not invention.
- **Forkability as a first-class design property** (per operator), so spinning
  up a sibling series later is config, not a rebuild.
- **Native distribution across vertical-short + long-form** without re-scripting:
  the long explainer is the *destination*, the shorts are *funnels* into it.

### Non-goals (v1)
- Not financial advice / not signal-selling. Build-in-public is about *building
  the tool*, not telling people what to trade. (Keeps us clear of compliance
  surface and matches the "personal operator tool" reality.)
- Not a polished studio production. Authenticity > gloss for this audience
  (builders, quants, indie-hackers, finance-curious devs).
- Not committing to specific forks yet — we design the seams, we don't pour
  concrete.

---

## 2. The core design tension (and how the hierarchy resolves it)

Short-form has a structural conflict:

- The algorithm serves each video **individually** to **cold** viewers → every
  episode must stand alone.
- A "series" implies **continuity and progression** → returning viewers want a
  path.

A hierarchical architecture resolves both at once, and it's the *same* shape the
platform already uses for knowledge (see `.claude/modules/video_vision.md` →
"atomic chunk → channel `_index.md` rollup → domain"):

```
Domain            Trading                         (forkable: → Fitness, → …)
  └─ Series       "Building a trading brain
                   in public"                     (the durable promise)
       └─ Arc     "Decisions that say no"         (3–7 episode cluster; the
                                                    returning-viewer path)
            └─ Episode  "I deleted my rules
                         engine. Here's why."      (atomic, self-contained,
                                                    20–60s)
```

- **Episode = leaf.** Self-contained, one idea, survives being served alone.
- **Arc = branch.** A thematic cluster that gives a binge path and a long-form
  destination.
- **Series = the promise.** What a subscriber signs up for.
- **Domain = the fork point.** Where a whole new sibling series buds off.

**Rationale:** this isn't an arbitrary taxonomy — it's the platform's own IA
reflected back. That coherence is itself build-in-public content ("I structured
my video series the same way I structured my knowledge base, and here's why").

---

## 3. The forking model (design-for-forkability)

The platform forked finance → fitness → nutrition by **reusing the same indexer
code with a different YAML scope** (`_domains.yaml`, per the multi-domain
briefing). The video series forks the **same way**:

> **The episode template + hook engine + production pipeline are
> domain-agnostic infrastructure. The domain is configuration.**

A leaf that gets traction becomes the seed of a new branch. When a Trading
sub-topic (say, "how I model macro regimes") consistently outperforms, it can
graduate from *arc* → its own *series*; and if the operator ever wants a wholly
different domain, that's a new *domain* row reusing the same template — exactly
the `cache-finance.db` / `cache-fitness.db` / `cache-nutrition.db` sibling
pattern.

**What we build now (the seams):**
- `domain` is a top-level field on every content row, not hardcoded copy.
- Episode templates reference *roles* ("the receipt", "the wrong turn"), not
  finance-specific content, so a fitness fork inherits the format for free.
- The hook library is organized by *psychological pattern*, not by subject.

**What we do NOT do now:** pick the forks. Per operator, forks are undecided;
we only guarantee they're cheap later.

---

## 4. The verifiability principle (the differentiator — inherited from the repo)

The repo already enforces **demo-branch verifiability discipline** (CLAUDE.md):
every numeric claim, named feature, or capability on the public demo must trace
to something that actually ships. **We adopt the identical rule for video:**

> **No episode claims a number, a feature, or an outcome that doesn't trace to a
> real artifact** — an ADR, a roadmap-shipped retro, a commit, a test count, or
> a live DB query.

This is not a constraint that limits us — it's the *entire pitch*. Finance
content is drowning in invented drama and unfalsifiable hype. A series where
every claim has a receipt (and where we openly show the *wrong* turns) is
differentiated precisely because it refuses to lie. The meta-episode "Why my
demo isn't allowed to lie" (source: demo-branch claim audit, 2026-05-12 retro)
*is* the series' thesis statement.

Practical rule: every episode brief carries a `source_ref` (see §7). If it can't
cite a source, it doesn't ship.

---

## 5. Episode anatomy

### 5.1 The universal beat sheet (every short)
| Beat | Time (45s short) | Job |
|---|---|---|
| **Hook** | 0–3s | Earn the next 3 seconds. A claim, a number, or a contradiction. |
| **Setup** | 3–10s | One sentence of problem/context. The "why should I care." |
| **Payload** | 10–30s | The *one* decision or insight. Exactly one. |
| **Proof** | 30–40s | The receipt — the number, the gotcha, the trade-off we accepted. |
| **Payoff / CTA** | 40–45s | The lesson generalized + soft pull to the long-form arc. |

The first 3 seconds carry ~80% of the retention outcome on TikTok/Reels; the
title + first frame carry it on Shorts. Budget creative energy accordingly.

### 5.2 Per-format mapping (one source, four cuts)
The shorts are the **same content** recut, not re-scripted:

| Format | Length | Frame | What changes from the master short |
|---|---|---|---|
| **TikTok** | 15–45s | 9:16 | Hardest, fastest hook; trend-aware audio; on-screen captions burned in. |
| **Reels** | 20–60s | 9:16 | Same cut as TikTok; aesthetic-forward cover frame for the grid; save-bait ending ("save this for when you over-engineer"). |
| **Shorts** | 30–60s | 9:16 | Same cut; *front-load the title text* (search + suggested driven); evergreen phrasing in title. |
| **Longer explainer** | 3–8min | 16:9 | The **arc destination** — stitches 3–5 related shorts into the full story: the options considered, the trade-offs, the sharp edges, the "trigger to revisit." This is where ADR depth lives. |

**Production implication:** script the long explainer per *arc*, then the
shorts are extracted clips/beats from it. One filming session → one long video →
N shorts. This is the leverage that makes "all four formats" sustainable.

---

## 6. The hook library (grounded in real artifacts)

Organized by **psychological pattern** (so forks inherit it). Every example
below is traceable to a real source in this repo — none are invented.

| Pattern | Template | Real instance (source) |
|---|---|---|
| **The wrong turn** | "I built X. Then I deleted it. Here's why." | "I built a rules-engine DSL, then chose *not* to." (ADR-007) |
| **The refusal** | "Everyone says do X. I didn't. Here's the math." | "Everyone adds Redis. One database, no regrets (yet)." (ADR-008) |
| **The surprising constraint** | "My [thing] has no [expected feature]. On purpose." | "My trading app has no dark mode — on purpose." (ADR-009) |
| **The receipt** | "[Big number]. Here's the one [detail] behind it." | "25 seconds → 87 milliseconds. The fix was one word." (`excerpts=false`, Vault-indexer Phase E retro, 2026-05-16) |
| **The lonely bug** | "This bug *only* happened in [narrow case]." | "The deadlock that only happened in SQLite, never in prod." (tv-context Phase 1 retro, 2026-05-17) |
| **The meta** | "I built an AI to do X. Today it's the subject." | "I built an AI that watches finance YouTube so I don't have to." (video-vision L2 retro, 2026-05-14) |
| **The honesty flex** | "My [public thing] isn't allowed to lie. Here's the rule." | Demo-branch claim audit (2026-05-12 retro) — also the series thesis. |
| **The grading** | "A prediction is worthless until you grade it." | Hit-rate-weighted opportunities + prediction_accuracy (signal layer). |
| **The argument** | "I let [N] AI agents argue about my [thing]." | Council-driven UX rework: architect/pragmatist/critic/skeptic/designer (2026-05-17 retro). |

**Hook hygiene** (build-in-public specific): the hook must be *true*. A hook that
over-promises relative to the payload violates the verifiability principle and
erodes the exact trust the series trades on.

---

## 7. In-platform feature (so deliverable #2 can be built next)

A new `app/content/` module that models the hierarchy **and** binds each episode
to its source artifact — closing a self-referential loop: *the platform tracks
the videos made about the platform, with provenance back to the shipped work.*
This directly operationalizes the verifiability principle.

### 7.1 Data model (mirrors existing `app/rx/`, `app/ticker_review/` patterns)
```
content_domains      id, slug ('trading'), title, status, created_at
content_series       id, domain_id→, slug, title, promise, status
content_arcs         id, series_id→, slug, title, theme, order_idx
content_episodes     id, arc_id→, slug, title,
                       hook_text, beat_sheet (JSON), status
                       ('idea'|'scripted'|'filmed'|'published'),
                       source_ref (TEXT),          -- e.g. 'adr:007',
                                                   --      'retro:2026-05-16-vault-phase-e',
                                                   --      'module:video_vision',
                                                   --      'commit:<sha>'
                       formats (JSON),             -- per-platform URLs once live
                       published_at, created_at
```
- **`source_ref` is the verifiability hook.** A lint/test can assert every
  `status='published'` episode has a resolvable `source_ref`.
- **`domain_id` at the top** makes forking a row insert, not a refactor (§3).
- Follow repo conventions: Alembic migration (`00NN_content.py`), Pydantic
  schemas at the edge, service layer server-stamps fields, `X-API-Key` reads.

### 7.2 Surfaces
- `GET /v1/content/tree` → the full Domain→Series→Arc→Episode tree (the
  editorial calendar / kanban backend).
- Frontend: a "Studio" page reusing the existing neumorphic primitives
  (`TabbedShell`, `StatusBadge`, `PageWithSidecar`) — episodes as a kanban by
  `status`, each card showing its `source_ref` as a deep link into `.claude/`.
- A small generator: `scripts/seed_content_from_repo.py` walks
  `.claude/decisions/` + `.claude/status/roadmap-shipped.md` and proposes
  episode `idea` rows pre-filled with `source_ref` — turning the docs into a
  backlog automatically.

> This module is **proposed**, not built. It's scoped here so production (#3)
> and the pilot (#4) can proceed first and inform the schema.

---

## 8. Season 1 — episode backlog (mined from real shipped work)

Series: **"Building a trading brain in public."** Every episode cites a source;
none are invented. Grouped into arcs.

### Arc A — "Decisions that say no" (the judgment arc)
| # | Working title | Hook pattern | Source |
|---|---|---|---|
| A1 | I deleted my trading rules engine | wrong turn | ADR-007 |
| A2 | One database. No Redis. No regrets (yet) | refusal | ADR-008 |
| A3 | My trading app has no dark mode — on purpose | surprising constraint | ADR-009 |
| A4 | One notification channel. That's the whole list | refusal | ADR-006 |
| A5 | I refused to automate the browser | refusal | ADR-016 |
| A6 | Why I ditched the no-code builder | wrong turn | ADR-001 |

### Arc B — "Making the machine see" (the video-vision saga)
| # | Working title | Hook pattern | Source |
|---|---|---|---|
| B1 | I built an AI that watches finance YouTube for me | meta | video-vision L2 retro (2026-05-14) |
| B2 | Can a 2-billion-parameter model read a candlestick? | grading | L3 Qwen2-VL retro (2026-05-14) |
| B3 | Teaching the machine the tickers it's never heard of | the receipt | ticker-review queue retro (2026-05-14) |
| B4 | 25 seconds → 87 milliseconds. One word | the receipt | Vault Phase E retro (2026-05-16) **← PILOT** |

### Arc C — "From prediction to P&L" (the signal layer)
| # | Working title | Hook pattern | Source |
|---|---|---|---|
| C1 | A prediction is worthless until you grade it | grading | prediction_accuracy / hit-rate weighting |
| C2 | My laptop and the cloud sync both ways, privately | meta | ADR-002 (Tailscale bidirectional sync) |
| C3 | The signal that ranks itself by how often it's right | the receipt | opportunities hit-rate weighting |
| C4 | From one click to a logged trade with attribution | meta | rx-finance "log trade from rec" retro (2026-05-16) |

### Arc D — "Build discipline" (how the sausage stays honest)
| # | Working title | Hook pattern | Source |
|---|---|---|---|
| D1 | Why my public demo isn't allowed to lie | honesty flex | demo claim-audit retro (2026-05-12) |
| D2 | I let 5 AI agents argue about my UI | the argument | council UX rework retro (2026-05-17) |
| D3 | The deadlock that only happened in SQLite | lonely bug | tv-context Phase 1 retro (2026-05-17) |
| D4 | 847 tests. Here's the one that earned its keep | the receipt | testing discipline (suite-count retros) |

> 18 episodes ≈ a full season across 4 arcs, with D1 doubling as the series'
> thesis statement. Every row maps to a `source_ref` for the feature in §7.

---

## 9. Pilot episode (full script — end-to-end, deliverable #4)

**B4 — "25 seconds → 87 milliseconds. The fix was one word."**
Chosen as pilot: self-contained, a killer number, a one-word fix, and a lesson
every dev feels. Source: Vault-indexer Phase E (Commit 1) retro, 2026-05-16
(`excerpts: bool = True` default silently ran a 25s per-result step until a
query param turned it off → 25s → 87–409ms warm).

**Master short — 45s, vertical (the TikTok/Reels/Shorts cut):**

> **[0–3s · HOOK]** (on screen: `25,000ms` ticking, then snaps to `87ms`)
> "This query took twenty-five seconds. The fix was *one word.*"
>
> **[3–10s · SETUP]**
> "My knowledge base kept timing out. Every search ran a step that re-ranked
> every sentence of every result — for results I was about to throw away."
>
> **[10–30s · PAYLOAD]**
> "The function had a default: `excerpts = True`. Always on. So even the callers
> that never used excerpts paid the full cost. I added one parameter —
> `excerpts=false` — for the path that doesn't need them."
>
> **[30–40s · PROOF]** (on screen: the retro line, real numbers)
> "Twenty-five seconds to eighty-seven milliseconds. Warm cache. Same results.
> No new infra."
>
> **[40–45s · PAYOFF / CTA]**
> "The expensive default nobody questioned. Full breakdown — and the three other
> retrieval fixes that came after — in the long one."

**Long-form destination (Arc B explainer, ~6min):** stitches B1→B4 — the whole
"making the machine see, then making it fast" arc, including the decay-model
rewrite, the query parser, and the lexical/RRF hybrid (all in the same retro).

**On-screen verifiability:** show the actual retro text / the diff. The receipt
*is* the content.

---

## 10. Production pipeline

```
Source artifact (ADR / retro / commit)
   → episode brief (hook + beat sheet + source_ref)        [§5, §7]
   → film/record the long-form arc explainer (16:9)
   → Descript: transcript-edit, captions, trim to beats     [Descript MCP available]
   → extract N vertical shorts (9:16) from the long master
   → per-platform cover frame + title (TikTok/Reels/Shorts) [§5.2]
   → publish; write formats[] URLs back to the episode row  [§7]
```

- **Reuse, don't reinvent:** the Descript integration handles assembly/captions.
  Note `tools/vault_indexer/ingest/video_vision.py` is an *ingest* pipeline
  (reading other people's videos into the vault) — it is **not** a production
  tool; don't conflate the two. The only crossover is thematic (B-arc is *about*
  that pipeline).
- **Cadence proposal:** one arc explainer + its 3–5 shorts per cycle. Sustainable
  because the backlog (§8) is pre-written and sources are immutable.

---

## 11. Deliverable sequencing & open questions

Operator asked for **all four**. Recommended order (each gates the next):

1. **This doc** — content architecture + curriculum. ✅ (this file)
2. **Pilot** (#4) — produce B4 end-to-end (script in §9) to validate the format
   *before* building tooling around it. Cheapest way to learn.
3. **In-platform feature** (#2) — build `app/content/` (§7) once the pilot
   tells us what metadata an episode actually needs.
4. **Production at cadence** (#3) — roll out Arc A/B with the validated template.

### Open questions for the operator (don't block this doc)
- **Series name** — "Building a trading brain in public" is a placeholder. Keep,
  or workshop?
- **Face/voice on camera, or screen-record + voiceover, or faceless captions?**
  (Changes the pilot's production approach significantly.)
- **Compliance posture** — confirm the "not financial advice, building-the-tool"
  framing is the line we hold (keeps us off signal-selling surface).
- **Publishing identity** — personal handle vs. a TradingV brand account? Affects
  whether the feature in §7 stores one `formats[]` set or per-channel variants.
- **Pilot first, or feature first?** This doc recommends pilot-first (step 2);
  confirm before I start producing or scaffolding code.

---

## See also
- [`.claude/modules/video_vision.md`](../modules/video_vision.md) — the ingest
  pipeline the B-arc is *about* (not the production tool).
- [`.claude/decisions/`](../decisions/) — the ADR backlog (Arc A + much of C/D).
- [`.claude/status/roadmap-shipped.md`](../status/roadmap-shipped.md) — the retro
  backlog (Arc B/C/D source material, with real numbers).
- [`CLAUDE.md`](../../Claude.md) — "Demo-branch verifiability discipline", the
  rule §4 inherits.
