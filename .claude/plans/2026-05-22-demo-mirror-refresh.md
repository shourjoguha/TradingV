# Demo mirror refresh — 2026-05-22

**Context:** Base app (`/TradingView `) has shipped ~13 days of work since
demo last refreshed (2026-05-09). Railway permanently shut down 2026-05-17
(ADR 018). New modules: rx, the_street, ticker_review, earnings,
video_vision, macro/sectors. Hypotheses + tv-context deeper. `.claude/`
reorganised into modules/guides/status folders.

**Constraint:** "general structure and philosophy of this repo does not
change." 4-tab layout stays (Today / Predictions / Motion / About). No
new pages, no live data, no secrets. Demo verifiability discipline
applies (base CLAUDE.md §"Demo-branch verifiability discipline").

**Council ruled** (council skill invocation 2026-05-22):
- Pragmatist load-bearing: demo still runs on Railway → calling out
  Railway-shutdown on About without caveat is a credibility self-own.
  Distinguish "base app architecture" vs "this demo's hosting".
- Critic load-bearing: stale-claim surface > About. Grep-audit FIRST.
- Skeptic load-bearing: skip ceremony. No `.claude/` folder mirror.
  System-map = text, not component.

## Phases

### Phase 1 — Audit (grep + scope)

- Grep every demo string for: `Railway`, `replica`, `Tailscale`,
  `always-on`, `sync`, `bidirectional`. List + classify (kill /
  caveat-as-historical / kill-and-replace).
- Catalogue all explicit and implicit capability claims in demo prose
  (DemoAbout, DemoHome, DemoMotion, DemoPredictions, DemoBanner,
  footer, canned.json, README, Claude.md, DEMO_DEPLOY.md).
- Write audit findings into `.claude/reviews/2026-05-22-claim-audit.md`.
- Retrospective.

### Phase 2 — Prose refresh: About + footer + banner

- DemoAbout: kill live-Railway claim; reframe topology section as
  "What the base app is" with one explicit "the demo you're reading
  is a snapshot, hosted on Railway+Cloudflare" caveat.
- STACK list updated: add Whisper-MLX, Qwen2-VL, Postgres-only,
  vault-indexer, Obsidian. Drop Tailscale-as-cross-machine-sync.
- New failure mode card or replacement: earnings calendar gate
  (replaces or augments existing copy where applicable).
- Add new pillars section (existing or new): vault-indexed research,
  TV-context vision summarisation, hypothesis invalidator, video
  ingest (Whisper + Qwen2-VL extracting tickers from YouTube).
- Each new pillar wears an "operator-surface — not in this demo"
  badge so we never overclaim.
- DemoBanner / footer reviewed for Railway/replica wording.
- Retrospective: re-grep, re-check verifiability discipline.

### Phase 3 — Demo-data payload refresh (verifiability-bounded)

- `manifest.json`: bump `entry_date` / `cutoff_date` / `scrub_version`
  to mark this pass. Add `system_pillars` array enumerating shipped
  capability with `surfaced_in_demo: bool` so the data drives any
  future system-map render and the verifiability check has a single
  source of truth.
- `today.json`: add an `attention_score` numeric to fresh_signals (so
  TV-context's attention-scoring pipeline gets a soft surface), keep
  existing fields untouched.
- `motion/opportunities.json`: add optional `attention_score` field.
- No new schema if it can't be filled by the bake script later.
- Retrospective: types still align with `frontend/src/demo/api.ts`?

### Phase 4 — Frontend payload binding (minimal)

- Update `demo/api.ts` types for optional `attention_score`.
- DemoHome fresh-signals list: show attention badge when present.
- DemoMotion opportunities table: optional column.
- About system-map: text-only "system map" section listing the
  pillars with their state (shipped, opt-in, operator-only,
  not-in-demo). No diagram component.
- Build check (`npm run build`); no Playwright (no live server).
- Retrospective.

### Phase 5 — Demo .claude/ snapshot refresh (low-effort, no folder
reshuffle)

- Update `.claude/architecture.md` (high-level): reflect Railway
  shutdown on base, vault-indexer multi-domain, new modules.
- Update `.claude/roadmap-shipped.md`: append summary entries for
  the ~13-day delta so the demo's `.claude/` accurately describes
  what base now is.
- Add `CHANGELOG.md` at repo root: human-readable mirror diary.
- DEMO_DEPLOY.md unchanged unless audit flagged it.
- Retrospective.

### Phase 6 — Final sweep + push

- Re-run grep audit; expected zero residual stale-claim hits.
- Run `npm run build` once more.
- Git add / commit / push to origin/demo.
- Retrospective doc in `.claude/reviews/`.

## Trade-off ledger (updated as phases land)

- **Trade-off T-01**: No `.claude/` folder mirror. Reason: Skeptic +
  Critic — implies parity of function the demo doesn't have. Cost:
  demo `.claude/` flat vs base nested. Mitigation: README ledger.
- **Trade-off T-02**: System-map as text not component. Reason:
  Pragmatist — every component is new bug surface. Cost: less visual
  punch. Mitigation: pillars enumerated in `manifest.json` data,
  rendered as a clean styled list with badges.
- **Trade-off T-03**: Add `attention_score` field even though
  scoring isn't surfaced anywhere else in demo. Reason: future bake
  script can fill it; explicit hint that the system has more than
  rule-based scoring. Cost: optional-field complexity. Mitigation:
  always optional; absent on the existing snapshot until next bake.

## Out of scope (deliberately)

- New tabs / pages
- Live data wiring
- Diagram components / animations
- Mirroring base's `.claude/modules/` folder shape
- Filling in walkthrough video IDs (operator's task)
