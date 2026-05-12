# External review — `anthropics/financial-services`

**Date:** 2026-05-09 · **Source:** https://github.com/anthropics/financial-services · **Read-only review; no changes proposed in this pass.**

> Sister to `2026-05-09-app-architecture-review.md` (our system, internal). This document evaluates Anthropic's reference implementation library for financial-services agents and asks: *what's worth borrowing, what's not, and what does it mean for our existing system?*

---

## §1. What that repo is in one paragraph

A reference library of **production-grade Claude agents + skills + MCP connectors** for financial services workflows. It ships 11 named agents (Pitch Agent, GL Reconciler, Market Researcher, Earnings Reviewer, Model Builder, Valuation Reviewer, Month-End Closer, Statement Auditor, KYC Screener, Meeting Prep Agent, plus the core financial-analysis bundle) backed by 44+ skills across seven verticals (investment banking, equity research, private equity, wealth management, fund admin, operations, financial-analysis core). Every agent is **dual-deployable** as either a Claude Cowork plugin or a Managed Agent via `/v1/agents`, sharing the same source. All external data flows through **MCP servers** (Daloopa, FactSet, Morningstar, LSEG, S&P Global, Moody's, PitchBook, Aiera, MT Newswires, Egnyte, Chronograph). Pure markdown + YAML + JSON; no build step.

Audience is enterprise FSI firms forking + customising. Not a runnable app — a templated library.

---

## §2. Architectural deltas vs our system

| Dimension | Anthropic FSI | Our app |
|---|---|---|
| **Audience** | Multi-firm, customisable | Single operator, opinionated |
| **Output medium** | Documents (pitch deck, CIM, Excel model) + spreadsheet edits | Decisions (UI, journaled trades, signals) |
| **Compute model** | Claude orchestrates skills + MCP tools; no autonomous loop | FastAPI app with daily Kronos forecast loop, hourly opportunities tick, weekly Claude research stress-test |
| **State** | Stateless agents + MCP-supplied data | Postgres + vault + indexer cache.db; long-running per-prediction journal |
| **Model usage** | Claude as orchestrator + writer | Kronos for prediction (no Claude); Sonnet only for Research stress-test + TV Context vision; Haiku for vault auto-tag |
| **Skills format** | Markdown-with-frontmatter as executable spec | We use the same format for `~/.claude/skills/` but **none of our backend logic is exposed as a skill yet** |
| **Data layer** | MCP servers (swappable per firm) | Direct yfinance/FRED/Gekko-scrape/TV-webhook (hardcoded) |
| **Compliance** | All outputs staged for human review | Same — research approve/dismiss, manual trade journal, no auto-execute |
| **Distribution** | Cowork plugin manifest + Managed Agent YAML | uvicorn binary + Vite SPA |

Key convergence: **both systems explicitly never execute orders or bind risk** — outputs are staged for human review. Different reasons (their compliance, our hand-built workflow), same shape.

Key divergence: **they're a template, we're a running app**. Their skills are reusable across firms; our backend logic is purpose-built and unfactored.

---

## §3. What's worth borrowing — ranked

### Tier 1 — High value, low effort

#### 1. Aiera MCP for earnings-call transcripts
**Their use:** `mcp-pub.aiera.com` — Aiera publishes earnings-call transcripts as an MCP tool. Claude can pull a clean transcript without scraping.

**Our gap:** Today we use Whisper to transcribe YouTube videos for newsletters/macro commentary. We have **no earnings-call ingest path at all**. Earnings is the highest-impact catalyst category and we're blind to it.

**Why this matters:** the `Earnings Reviewer` agent in their repo is built around this exact data source. Wiring Aiera as an MCP server in our backend (similar to how `app/research/bundle.py` already calls the vault-indexer over HTTP) gives us earnings transcripts on tap. Slot them into TV Context with `kind='earnings_transcript'` or as a new vault folder `Videos/earnings-calls/`.

**Effort:** ~1 day. Add `aiera` MCP to a new `app/mcp_clients/` module, expose `/v1/mcp/aiera/transcript?ticker=...&quarter=...` proxy, add a Today panel surfacing recent earnings hits across the roster.

**Caveat:** Aiera is a paid SaaS; check their MCP access tier and rate limits.

#### 2. MT Newswires MCP for breaking news
**Their use:** `vast-mcp.blueskyapi.com/mtnewswires` — newswire feed.

**Our gap:** No structured newswire ingest. Operator gets news from Twitter/RSS scattered.

**Effort:** ~1 day if their MCP is accessible. New `tv_context.kind='news'` row per item.

#### 3. Skills folder for our backend workflows
**Their pattern:** every analysis (DCF, comps, IC memo, thesis tracker) is a markdown skill with frontmatter (`name`, `command`, `description`, methodology) — Claude reads it and structures output to match.

**Our gap:** our research stress-test prompt is hand-built in `app/research/prompts.py` and the operator can't easily add a new research workflow without code edits. Adding "stress an earnings catalyst" or "value vs growth regime check" requires Python.

**Why this matters:** if we factor `app/research/prompts.py` content into `~/.claude/skills/<workflow>.md` files (mirror their layout), the operator gains the ability to drop a new research flavour by writing a markdown file. Same Claude API call shape; different orchestration. **Their skills directly map to research workflows we already do or want to do:**

| Their skill | Our nearest analogue | Status |
|---|---|---|
| `comps-analysis` | None — we don't peer-rank | **gap** |
| `earnings-analysis` | TV Context + Research, but unstructured | **gap** |
| `thesis-tracker` | Hypothesis module — convergent | already built |
| `model-update` (post-earnings) | Trade-close enrichment is adjacent, not the same | **gap** |
| `portfolio-monitoring` | Trades + accuracy — convergent | already built |
| `deal-screening` | The Street tier classification — convergent in spirit | already built |

**Effort:** ~2-3 days to factor existing prompts into 3-4 skills + add a skill-loader to `app/research/service.py`.

### Tier 2 — Medium value, medium effort

#### 4. MCP-pluggable data layer for our market_data + macro modules
**Their pattern:** MCP servers in `.mcp.json`. Want to swap FactSet for Bloomberg? Edit one JSON entry, no prompt rewrites.

**Our coupling:** `app/market_data/providers/yfinance.py` and `app/macro/providers/yfinance.py` are hand-coded against yfinance's Python lib. Switching providers means rewriting both modules.

**Why this matters:** yfinance is unreliable (we already see 6 `HTTP 404` errors per cycle in the backend log; PENG, LGN regularly fail). Wrapping our providers behind a Protocol that an MCP client could implement is a 1-day refactor that gives us option value when yfinance breaks for good.

**Don't actually swap providers yet.** Just refactor the seam. The MCP pattern is the discipline; the implementation can stay yfinance.

#### 5. Steering events for the daily research-weekly loop
**Their pattern:** in Managed Agent mode, the orchestrator emits `steering_event` messages that prioritise an agent's decisions. Example: `gl-reconciler` gets `break_found` events with metadata, uses them to pick which break to investigate first.

**Our gap:** the weekly research loop in `app/research/weekly.py` walks every active hypothesis in order. There's no priority signal — a hypothesis with imminent invalidation gets the same attention as one with 5 months of TTL left.

**Why this matters:** hypotheses with `at_risk = true` (TTL ≤ 30d) or with recent contradictory evaluations should be stressed first. Drift alerts on tickers attached to a hypothesis should bump priority.

**Effort:** ~1 day. Pre-rank the hypothesis list before passing to the loop; structured event log → JSON to disk for audit.

#### 6. Sync script as drift detector for our markdown skills
**Their pattern:** `sync-agent-skills.py` keeps bundled skill copies in lock-step with the source. CI fails if drifted.

**Our adjacent tool:** we don't bundle skills, we just have `~/.claude/skills/` from the global Anthropic skills layer. But when we factor research prompts into skills (item #3 above), we'll face the same drift problem if we ever copy skills into the repo for portability.

**Effort:** trivial once #3 lands — copy their script verbatim.

### Tier 3 — Low value or out of scope

| Item | Why deferred |
|---|---|
| Pitch Agent / CIM authoring / Excel model builder | We don't generate documents. Our output is decisions, not deliverables. |
| Microsoft 365 add-in | We have no enterprise distribution surface. Single operator. |
| Dual-deploy (Cowork + Managed Agent) | We're a long-running FastAPI app, not an agent invoked on demand. |
| Daloopa / FactSet / Morningstar MCP | Subscription-tier data; cost not justified at single-operator scale. yfinance + FRED + Gekko cover us. |
| KYC Screener, GL Reconciler, Statement Auditor, Month-End Closer | Different domain (corporate finance ops). Operator doesn't run a fund admin shop. |
| Wealth-management skills (financial plan, TLH, client review) | Operator is the client, no third-party clients to advise. |
| Plugin marketplace distribution | Single user, no audience to distribute to. |

---

## §4. Patterns we already share (convergent design — sanity check)

- **Markdown-with-frontmatter as the operator-facing config layer.** Their skills, our `_index.md` vignettes, our `_channel.yaml`, our vault frontmatter. Both projects treat editable markdown as the source of truth.
- **Audit-trail-by-default.** Their staged outputs, our `Research/<id>.md` + approve/dismiss queue. Both projects assume the human re-reads everything.
- **MCP-style data abstraction.** Their `.mcp.json`, our `app/research/bundle.py:_retrieve_evidence` calling the vault-indexer over HTTP. Same separation of concerns; different implementation.
- **Compliance as prompt constraint, not technical barrier.** Both repos rely on "the agent isn't told how to execute" rather than putting hard fences in code. (Whether this is wise is a separate conversation. We agree with their stance for the same reasons — single human in the loop.)
- **No build step for the config layer.** Their everything-is-markdown ethos, our `.claude/` + vault + `~/.claude/skills/` ethos. Both projects deliberately keep the "human-readable layer" out of the JS/Python build pipeline.

---

## §5. Files in their repo worth studying further

For when we actually pick up an item from §3:

| If picking up | Read | What you'll learn |
|---|---|---|
| Aiera MCP wiring (item #1) | `plugins/vertical-plugins/financial-analysis/.mcp.json` + the Earnings Reviewer agent | Concrete MCP client config + the prompt patterns that consume earnings transcripts |
| Skills factoring (item #3) | `plugins/vertical-plugins/equity-research/skills/earnings-analysis.md` + `plugins/vertical-plugins/equity-research/skills/thesis-tracker.md` | Their skill frontmatter conventions; their methodology format |
| MCP pluggability (item #4) | `plugins/vertical-plugins/financial-analysis/.mcp.json` + how skills reference MCP tools by name | The level at which MCP is wired (per-plugin manifest, not per-agent) |
| Steering events (item #5) | `managed-agent-cookbooks/<any agent>/agent.yaml` + `scripts/orchestrate.py` | Event-loop pattern for handoffs and priority signals |
| Sync discipline (item #6) | `scripts/sync-agent-skills.py` + `scripts/check.py` | The "fail CI on drift" pattern |

---

## §6. Recommended sequence (if we decide to act)

If you want to pull from this repo, do it in this order — each step independent, each delivers value alone:

1. **Aiera MCP integration (~1 day)** — earnings transcripts. Highest single-piece value-add. Drops cleanly into TV Context.
2. **Skills extraction for research prompts (~2-3 days)** — operator can add a new research flavour by writing markdown. Sets up #4 and #5.
3. **MCP-pluggable seam in market_data + macro (~1 day refactor)** — Protocol-shaped abstraction, keep yfinance underneath. Option value when yfinance breaks.
4. **Steering events in weekly research loop (~1 day)** — prioritise at-risk hypotheses, log priority events to disk for audit.
5. **MT Newswires MCP** if/when item #1 proves the pattern works.

Total: ~1 week of focused work, every step optional, each delivers value alone. Nothing on this list requires architectural changes — it's all additive.

---

## §7. What we should NOT do

1. **Do not rewrite our backend as a Cowork plugin.** Our app is a long-running stateful service, not an on-demand agent. Their plugin model assumes Claude is the runtime; ours assumes FastAPI is the runtime, Claude is one tool inside it.
2. **Do not adopt their full vertical structure.** We don't have seven workflows; we have one (trading decisions). Inheriting `private-equity/`, `wealth-management/`, `fund-admin/` directories would just be cargo-culted folders.
3. **Do not subscribe to enterprise data MCPs (Daloopa, FactSet, Morningstar) yet.** Cost-prohibitive at our scale. Only consider when we have a workflow that demonstrably can't be served by yfinance + FRED + Gekko + earnings transcripts.
4. **Do not adopt their pitch-deck / CIM / model-builder skills.** Wrong output shape. Our deliverables are dashboard panels and journaled trades, not Word + PowerPoint files.
5. **Do not adopt their dual-deployment pattern.** We don't have two deployment targets; we have one (laptop + Railway replica of the same app).

---

## §8. Closing — what their repo actually proves

Their repo is the cleanest published demonstration that **Claude-orchestrated financial workflows are productionable in 2026**. Specifically it proves:

- MCP servers are mature enough to be the data layer for serious analysis (10+ providers wired in production).
- Markdown skills with frontmatter are sufficient as agent specifications (no DSL, no YAML schema).
- Subagent delegation via `handoff_request` events is a working pattern at the orchestration layer (in Managed Agents).
- The Anthropic API + Cowork + Managed Agents trio is enough infrastructure for a 44-skill, 11-agent library.

For us, **the repo's value is mostly as a catalogue of MCP integrations and skill conventions**, not as a deployment template. Our system is too purpose-built and too single-user to benefit from their plugin mechanics. But three of their MCP integrations (Aiera, MT Newswires, optionally LSEG) plug directly into gaps we have today, and their skill format would let us factor the research stress-test prompts into operator-editable artefacts.

The right move is **adopt selectively** (Tier 1 + parts of Tier 2 in §3), **ignore the rest** (§7), and **revisit annually** as their MCP catalogue grows.
