# Demo branch — changelog

Human-readable diary of what changed on the public `demo` branch and what
in the base app (`main`, `/Users/shourjosmac/Documents/Claude/TradingView`)
this branch is a snapshot of. The demo never carries live data, secrets,
or live runtime — see [`Claude.md`](Claude.md) for philosophy and
[`DEMO_DEPLOY.md`](DEMO_DEPLOY.md) for hosting.

## 2026-05-22 — mirror refresh

**Demo-branch changes:**
- Prose refresh on DemoAbout, AskWidget, `demo-data/canned.json`, root `Claude.md`:
  no more "live Tailscale + Railway replica" claim. Frames the historical
  Railway replica as retired 2026-05-17 (base [ADR 018](.claude/decisions/018-railway-shutdown.md))
  and distinguishes the demo's own Railway+CF Pages hosting from the base
  topology.
- New "System map" section on About listing 10 system pillars with explicit
  `in demo` vs `operator-only` badges (predictions / opportunities + per-rule
  attribution / drift detection / vault-indexed research / TV-context vision
  / hypothesis layer + invalidator DSL / earnings calendar / video-vision
  ingest / ticker review queue / macro+sectors workbench).
- `demo-data/manifest.json` schema bumped to v2: adds `system_pillars[]`,
  `base_branch_as_of`, `snapshot_refreshed_at`.
- `demo-data/today.json` + `demo-data/motion/opportunities.json`: optional
  `attention_score` field stamped on a sample of rows so the TV-context
  attention pipeline gets a soft surface in the demo without overclaiming
  coverage.
- Frontend: `frontend/src/demo/api.ts` types extended (optional
  `attention_score`, `SystemPillar` interface, manifest fields). DemoHome
  fresh-signals list shows an `ATTN xx` badge when the score is present.
- `.claude/architecture.md` + `.claude/roadmap-shipped.md` headers now mark
  themselves as 2026-05-09 snapshots; new readers are pointed at this
  CHANGELOG and the base repo for current state.
- This file (`CHANGELOG.md`) created.

**Base app shipped since 2026-05-09 (NOT mirrored in demo, listed for
reference):**
- Railway replica permanently retired 2026-05-17 ([ADR 018](.claude/decisions/018-railway-shutdown.md)).
- Modules added: `rx/` (finance-only prescription layer, local-Postgres-only),
  `the_street/` (smart-money tier dashboard), `ticker_review/` (unknown-symbol
  inbox), `earnings/` (calendar gating), `admin/` (loop registry, app
  settings, kill switch).
- Module deepened: `hypotheses/` (invalidator DSL: `tv_context_count_since`,
  `tv_context_stance_count_since`); `tv_context/` (attention score +
  Hypothesis-link table); `macro/` (sectors workbench: cycle wheel,
  rotation-bump chart, correlation heatmap with rolling-pair drill-in).
- `tools/vault_indexer/` went multi-domain: three sibling instances on
  `:8001` (finance), `:8002` (fitness), `:8003` (nutrition), registry-driven
  scope from `<vault>/_domains.yaml`.
- `tools/vault_indexer/ingest/video_vision.py`: Whisper-MLX + Qwen2-VL
  YouTube channel auto-ingest pipeline (3-stage structured chart-reference
  extraction, opt-in per `_channel.yaml`).
- New ADRs 010-018 (self-healing OHLCV fetch, macro storage shape,
  hypothesis object, vault-indexer, research stress-test, TV-context
  no-browser-automation, TV-context vision default-on, Railway shutdown).
- Base `.claude/` reorganised into `modules/`, `guides/`, `status/` folders
  with folder READMEs. Demo's `.claude/` deliberately not reorganised
  (council 2026-05-22 — implies parity of function that the demo facade
  doesn't have; mirror-by-prose is enough).

**Trade-off ledger** — decisions made during this refresh:
- **T-01** No demo `.claude/` folder mirror. Skeptic + Critic flagged
  ceremony cost + parity-implication risk. Cost: demo `.claude/` stays
  flat. Mitigation: this CHANGELOG.
- **T-02** System map rendered as text list, not diagram component.
  Pragmatist: every component is new bug surface. Cost: less visual
  punch. Mitigation: badges + structured data in `manifest.json`.
- **T-03** `attention_score` field added even though the TV-context
  pipeline isn't otherwise surfaced. Cost: optional-field complexity.
  Mitigation: always optional; absent on most rows (matches reality —
  not every ticker has recent TV-context coverage).
- **T-04** Skipped surfacing `rx/` and `the_street/` on About. They are
  operator-only and brand-name-coupled; surfacing them would either
  overclaim (no product to ship) or read as toy-project (single-operator
  smart-money curation). Mentioned obliquely in the "Earnings calendar
  gating" pillar where `the_street` tier-1/2 names are the trigger
  source.

## 2026-05-12 — claim audit + trim

See base `roadmap-shipped.md` retro from 2026-05-12. Five hard overpromises
and six soft overpromises were trimmed (fictional rule names → real
`R1/R2/R3` labels, walkthrough placeholder visibility gated, automatic
research-stress-test caveated as opt-in, separate TV-webhook vs
screenshot-paste paths documented).

## 2026-05-09 — first frozen snapshot

Initial demo cut. See `git log demo --oneline` for the granular history;
key commits include `c3d6c3a` (strip backend to read-only), `2f46cc7`
(dedicated read-only demo frontend), `042cd6c` (deployment guide for
Railway + Cloudflare Pages), `90cd268` (richer synthetic data + neumorphic
theme + per-rule attribution).
