# Macro Workbench — Brainstorm capture (2026-04-30)

> **Status:** Pre-plan. Captured from a brainstorm session, not yet committed to a phase.
> **Owner decisions still pending:** specific hypothesis seeds (#5 below), TTL defaults per regime axis.
> **Related:** [roadmap.md](../status/roadmap.md), [opportunities.md](../modules/opportunities.md), [trades.md](../modules/trades.md), [predictions.md](../modules/predictions.md).

## North-star

**Regime-aware research workbench**, not a macro dashboard. Closes the loop:

```
macro signals  →  hypotheses  →  Kronos opportunity context  →  trade  →  per-hypothesis P&L
```

Without that loop, a macro page is decoration. The unique wedge against Koyfin / MacroMicro / Crescat: **local DB + LLM reasoning** on top of curated views. The operator can ask *"does Costa's debasement thesis still hold given the last 6 months of our data?"* and get a structured, evidenced answer.

Three layers, in dependency order:

| Layer | What | Built on |
|---|---|---|
| 1 — Signals | Ratios + macro series; nightly pull; weekly resolution; 5y default zoom | yfinance + FRED |
| 2 — Hypotheses | Named view registry + first-class `Hypothesis` object with status lifecycle | Postgres + UI |
| 3 — Reasoning | LLM `/research/ask` with view-scoped DB context | Anthropic API |

## Anchoring constraints (from the operator)

- **80% trades long-horizon (months–years), 10% weekly, 10% intraday.** → Macro update cadence is **nightly**; default chart zoom is **5y daily**. No realtime feeds. Drop intraday breadth.
- **Public sources only for now.** No paywalled data; no RSS/Substack scraping in v1. May open up later via MCP (notebookLM, n8n) if a specific source is worth the cost. Embed TradingView for charts FRED/yfinance can't render.
- **Hypotheses must auto-deprecate (TTL) AND be manually cancellable.** Discipline lever — without it the log fills with always-bullish-on-gold takes that never close. Manual cancel covers "new info changed my mind." TTL covers "I forgot to revisit."
- **Goal is to trade more frequently with higher confidence**, not to add more chart-watching surface. Every artifact must connect back to a stated hypothesis or it's decoration.

## Twelve ratios — the v1 signal layer

Two columns of six. Anything beyond this is a TradingView embed.

| Regime axis | Ratio / series | Tickers | What it tells the operator |
|---|---|---|---|
| **Inflation** | Gold / SPX | `GC=F` / `SPY` | Hard-asset vs paper-asset preference (Costa) |
| | Copper / Gold | `HG=F` / `GC=F` | Reflation vs recession; leads 10Y |
| | Oil / Gold | `CL=F` / `GC=F` | Energy-led vs monetary inflation |
| **Growth** | Equal-weight / Cap-weight | `RSP` / `SPY` | Breadth / concentration |
| | Small / Large | `IWM` / `SPY` | Risk appetite at small-cap |
| | EM / DM | `EEM` / `SPY` | EM vs DM cycle |
| **Liquidity** | Fed balance sheet | FRED `WALCL` | Leading indicator (Costa, Druckenmiller) |
| | 5Y5Y inflation expectations | FRED `T10YIE` | Forward inflation regime |
| | Yield curve (10Y − 2Y) | FRED `WGS10YR` − `WGS2YR` | Recession leading indicator |
| **Stress** | High-yield / Investment-grade | `HYG` / `LQD` | Credit-risk preference |
| | Bonds / Equity | `TLT` / `SPY` | Bond bid vs equity bid |
| | Dollar | `DX-Y.NYB` | Dollar regime |

Plus a **9-cell sector strip** (XLK/XLF/XLE/XLV/XLI/XLP/XLY/XLU/XLB each ÷ SPY). Subsumes "sector heatmap" without a new visualization.

Plus a **slow regime panel** for multi-decade theses: `M2SL`, `WALCL` (already above), debt/GDP `GFDEGDQ188S`, deficit/GDP `FYFSGDA188S`, Treasury General Account `WTREGEN`, World Gold Council central-bank gold purchases (quarterly, scraped or manual).

## Things explicitly dropped

- ❌ DAX / KOSPI / Nikkei as standalone — replaced by `EFA/SPY` and `EEM/SPY`.
- ❌ "DXY alone" — keep DXY but add `EUR/USD` and `USD/JPY` separately (yen and euro have different stories).
- ❌ Sector heatmap as a visualization — already implicit in the sector-vs-SPY strip.
- ❌ Realtime macro updates, VIX term-structure, put/call — wrong cadence for long horizons.
- ❌ "Specific people" follow-list (gurus' personal trades) — picking gurus is identity, not signal.
- ❌ Putting macro through Kronos — macro is a feature for a future secondary model, not a target.

## Things deferred to v2+

- 13F + Form-4 ingestion (`openinsider.com`, `whalewisdom.com` free tier). Slow signal, fits long horizon, but adds ingestion complexity. After the loop is proven.
- Backtest engine that replays hypothesis status over history → per-hypothesis P&L attribution. Phase 6 of the plan below.
- Guru commentary scraping (Costa monthly letters, Crown YouTube transcripts) into the LLM context. Currently public-only without scraping.

## The Hypothesis object (Layer 2)

Schema sketch — first pass, will harden in plan phase:

```
hypothesis(
  id              UUID PRIMARY KEY,
  slug            TEXT UNIQUE NOT NULL,      -- stable, URL-safe identifier
  parent_id       UUID REFERENCES hypothesis(id), -- nullable; sizing-dependency (parent governs structural, child governs tactical)
  precondition_id UUID REFERENCES hypothesis(id), -- nullable; existence-dependency (precondition violated → this auto-cancels with reason 'precondition_failed')
  name            TEXT NOT NULL,
  thesis_text     TEXT NOT NULL,             -- markdown, free-form
  expected_dir    TEXT NOT NULL,             -- 'long' | 'short' | 'spread' | 'regime_shift'
  claim_type      TEXT NOT NULL,             -- 'absolute' | 'relative' | 'absolute_with_relative_signal'
  primary_metric  TEXT,                      -- the symbol/ratio whose move = success
  tracking_signal TEXT,                      -- early-warning ratio (often relative even when claim is absolute)
  ratios          JSONB NOT NULL,            -- full list of ratios/series watched
  invalidators    JSONB,                     -- conditions that auto-flip status to violated
  source_url      TEXT,                      -- link to the original commentary
  status          TEXT NOT NULL,             -- 'active' | 'confirming' | 'violated' | 'stale' | 'cancelled'
  ttl_until       TIMESTAMPTZ NOT NULL,      -- auto-deprecate after this
  cancelled_at    TIMESTAMPTZ,               -- manual abandon
  cancelled_reason TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)

hypothesis_evaluation(
  id              UUID PRIMARY KEY,
  hypothesis_id   UUID REFERENCES hypothesis(id) ON DELETE CASCADE,
  evaluated_at    TIMESTAMPTZ NOT NULL,
  status_before   TEXT,
  status_after    TEXT,
  evidence_json   JSONB                       -- snapshot of ratio values + verdicts
)
```

**Lifecycle:**
- Default TTL: 12 months (long horizon). Operator overrides per hypothesis.
- Nightly job recomputes status. If `now > ttl_until` and `status = 'active'` → `'stale'`.
- Invalidators (e.g. `"GC=F/SPY < its 200dma"`) flip → `'violated'`.
- Confirming evidence (e.g. ratio crossing a threshold in expected direction) flips → `'confirming'`.
- Manual `POST /v1/hypotheses/{id}/cancel` with reason.

**Parent / child semantics (`parent_id`) — sizing dependency:**
- A child can be `violated` while the parent stays `active`. Child invalidators are deliberately tighter than the parent's; they govern *tactical* sizing while the parent governs *structural* sizing.
- Cancelling a parent does NOT auto-cancel children — operator decides whether to re-anchor the children to a new parent or close them.
- Use case: same thesis at two horizons (e.g. 18mo tactical confirmation + 36mo structural). See seeded `latam-breakout-18m` ⇢ `latam-breakout-36m`.

**Precondition semantics (`precondition_id`) — existence dependency:**
- If the precondition becomes `violated` (or `cancelled`), the dependent hypothesis **auto-cancels** with reason `precondition_failed`. Cascade is one-way; cancelling the dependent does not affect the precondition.
- Different from parent/child: parent failure does NOT cascade; precondition failure DOES.
- Use case: a tactical timing claim that gates a magnitude claim. See seeded `btc-bottom-3m` ⇢ `btc-rally-24m` (24mo rally is meaningless if no bottom forms in 3mo).
- Operator can manually resurrect a dependent (after re-filing the precondition) — auto-cancellation captures `cancelled_reason = 'precondition_failed'` so it's visible in the lifecycle log.

**Claim type semantics:**
- `absolute` — success = the primary metric goes up/down regardless of comparison.
- `relative` — success = ratio outperforms; absolute level irrelevant.
- `absolute_with_relative_signal` — claim is absolute, but `tracking_signal` is relative because relative breakdowns lead absolute ones (early warning). Common shape for long-horizon theses.

## The View Registry (Layer 2)

A view = a reproducible bundle of charts + the hypothesis it tests + the source link. Five seeds at v1:

1. **Costa — Debasement thesis** (gold, copper/gold, Fed BS, breakevens)
2. **Crown — Breadth check** (RSP/SPY, IWM/SPY, sectors strip, % above 200dma)
3. **Druckenmiller — Liquidity primacy** (Fed BS, M2, TGA, USD)
4. **Dalio — End-of-debt-cycle** (debt/GDP, deficit/GDP, real yields, gold)
5. **Burry — Credit stress** (HYG/LQD, yield curve, distressed indices)

Each view links its `hypothesis_id`. Operator can clone a view, edit the chart bundle, save under a personal name. View registry is markdown + frontmatter, not a CMS.

## The Reasoning endpoint (Layer 3)

```
POST /v1/research/ask
{
  "question": "Does the debasement thesis still hold?",
  "hypothesis_id": 7,        // or "view_slug": "costa-debasement"
  "time_range": "6m"         // optional; default = since hypothesis.created_at
}
→
{
  "thesis_recap": "...",
  "supporting_evidence": [{"ratio": "GC=F/SPY", "as_of": "...", "value": "...", "interpretation": "..."}],
  "contradicting_evidence": [...],
  "current_status": "confirming",
  "suggested_observation": "Watch for 5Y5Y breakevens to cross 2.6% before adding."
}
```

Server-side: LLM gets the DB schema, the view's chart data, recent evaluations, and (later) scraped commentary. Returns a structured response — never just prose. Structured = the operator can feed it back into the next call.

## How macro feeds Kronos (the loop)

Each Opportunity row gains a tag list of hypotheses currently `confirming` or `violating`. Trades inherit the tags. Closed trades produce per-hypothesis P&L attribution — same shape as the existing per-rule attribution. The operator can answer:

> *"Has every Kronos opportunity I took during a `confirming` 'Druckenmiller liquidity' regime outperformed the average?"*

That single answer converts the workbench from passive to closed-loop. It's the reason this isn't another macro dashboard.

## Six-phase plan

| Phase | What | Scope | Why ordered here |
|---|---|---|---|
| **M-1** | Signal layer | 12 ratios + 6 FRED series + 9 sector ratios; nightly cron; storage in `macro_series` table; `/v1/macro/series` endpoint | Foundation. No system without data. |
| **M-2** | Hypothesis object + view registry | Schema + 5 seeded views + CRUD endpoints + UI panel | The novel layer. Even without LLM this beats Koyfin. |
| **M-3** | Wire macro into Opportunities + Trades | Tag rows w/ `confirming`/`violating` hypotheses; surface in UI | Closes the loop. Smallest scope that delivers the wedge. |
| **M-4** | LLM `/research/ask` endpoint | View-scoped DB context; Anthropic API; markdown structured output | "Ask my database" moat. |
| **M-5** | Insider / 13F ingestion | `openinsider.com` Form 4 cluster buys; WhaleWisdom 13F top-25 deltas; tag hypotheses with these as inputs | Slow signal, fits long horizon. After loop is proven. |
| **M-6** | Hypothesis backtest engine | Replay status over history; per-hypothesis P&L attribution from closed trades | Trade-confidence payoff. The "did this thesis make me money?" answer. |

Phases M-1 → M-3 are the foundation + closed loop. M-4 is the unique wedge. M-5 + M-6 are lock-in.

## Open questions / risks

1. **Maintenance discipline** — riskiest assumption. If the operator stops writing hypotheses after week 2, M-2 fails as designed. Mitigation: "Save view + open hypothesis dialog" must be a single button. Hypothesis writing must be ≤ 30 seconds.
2. **TTL defaults per axis** — long-horizon theses (debasement, debt cycle) need 24-month TTLs; tactical theses (sector rotation) need 3-month TTLs. Defaults should encode this.
3. **Invalidator language** — operator-authored conditions need to be expressive enough to encode "ratio < its 200dma for N consecutive days" without becoming a DSL. Start with a small enumerated set; widen only on demand.
4. **Public-source ceiling** — at some point Costa-grade analysis needs his actual letters in the LLM context. Defer until M-4 ships and is in use; revisit licensing/scraping then.
5. **Scope creep into "another Twitter"** — temptation to ingest commentary feeds is high. Keep it manual: operator pastes a URL into a hypothesis, the LLM fetches once on creation. No streaming feeds.

## Suggested next actions

1. **Operator action (no code):** seed three real hypotheses today as markdown drafts in `.claude/hypotheses/draft/`. If you can't write three in 30 minutes, the workbench premise is shakier than we think and we should re-scope before any code.
2. **Plan phase for M-1:** lock the 12 ratios + 6 FRED series, decide table shape (`macro_series(symbol, source, ts, value, ...)`), write a one-shot ingestion script, then schedule it.
3. **Plan phase for M-2:** write the migration + Pydantic schema + endpoints; ship behind a feature flag so the unfinished UI doesn't appear in the sidebar.

## Cross-references

- Roadmap candidate added in [roadmap.md](../status/roadmap.md) as item M-1.
- See `.claude/hypotheses/draft/template.md` for the seed template.
- LLM reasoning endpoint will live alongside `/v1/accuracy/*` — same patterns: nightly batch + on-demand POST.
