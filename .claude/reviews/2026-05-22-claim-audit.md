# Demo claim audit — 2026-05-22

Pre-flight scan before refreshing demo prose against the 2026-05-21 base.

## A. Stale-claim hits (Railway / Tailscale / replica)

### A1. User-facing demo prose — MUST refresh

| File | Lines | Stale claim | Disposition |
|---|---|---|---|
| `frontend/src/demo/components/AskWidget.tsx` | 27, 51, 63, 81 | "synced to Railway replica" / "Tailscale for laptop ↔ Railway sync" / "syncs laptop ↔ Railway via Tailscale" | Replace with historical caveat: "originally a Tailscale-synced laptop+Railway pair; Railway replica retired 2026-05-17 — laptop is now sole runtime. This demo is a frozen snapshot hosted on Railway+CF Pages for cheap, idle public showcase." |
| `frontend/src/demo/pages/DemoAbout.tsx` | 29-31 (STACK), 136-138 (topology section) | "Tailscale", "Railway" in stack; "Tailscale connects it to a Railway always-on replica that absorbs reads and webhooks" | Drop Tailscale + Railway from STACK (no longer load-bearing on base). Rewrite topology paragraph: "One operator's laptop runs the model + DB + ingestion + vault. The demo you're reading is a frozen JSON snapshot, hosted on Railway + Cloudflare Pages so it stays cheap and always-on; the live system retired its Railway replica 2026-05-17." |
| `Claude.md` (repo root) | 5, 22, 56, 85, 87-92 | Whole "Bidirectional Tailscale sync between laptop and Railway (always-on replica)" + Setup (Railway) block | Reword overview: drop "bidirectional ... replica" — base topology is now laptop-only; demo Railway is the demo's own static host, not a base replica. |

### A2. Self-referential (demo IS on Railway) — KEEP, optionally clarify

| File | Lines | Reason kept |
|---|---|---|
| `frontend/src/demo/api.ts` | 3, 7 | comment + default URL describe the demo's own host. True. |
| `app/main.py` | 5 | "the strip-down deployed to Railway as the public showcase" — demo's own host. |
| `DEMO_DEPLOY.md` | entire file | demo deployment guide; this is the demo's own infra, distinct from base's retired replica. Optional: one-line note that this is the demo's host, not the base's old Railway replica. |

### A3. Demo `.claude/` docs (stale snapshot of base pre-2026-05-17)

All under `.claude/*.md` — architecture, principles, sync, schedule, glossary, etc. They accurately describe the base **as of 2026-05-09** (when demo was last refreshed). They're snapshots, not active operational docs.

Disposition per council Phase 5: update `.claude/architecture.md` + `.claude/roadmap-shipped.md` headers to mark them as "snapshot, base has since shipped further changes — see `CHANGELOG.md`". Don't sweep every cross-link.

### A4. Legacy non-demo frontend (under `IS_DEMO=true` guard, dead code on this branch)

| File | Status |
|---|---|
| `frontend/src/components/Layout.tsx`, `frontend/src/pages/Research.tsx`, `frontend/src/pages/TVContextInbox.tsx`, `frontend/src/lib/backend-store.ts`, `frontend/src/lib/types.ts`, `frontend/src/vite-env.d.ts`, `frontend/src/docs/metrics.md` | All gated behind `IS_DEMO=true` in `App.tsx`. Never reachable in prod. Skeptic-rule: leave alone, don't expand surface. |

## B. Shipped-but-unsurfaced capabilities

Base has shipped these since 2026-05-09. The demo prose currently surfaces zero of them. Each gets one decision: surface (with operator-gate badge) / mention-only / skip.

| Capability | Demo treatment | Reason |
|---|---|---|
| **Vault-indexed curated research corpus** | ALREADY mentioned (DemoHome "what it's curious about" + AskWidget) — keep, augment with explicit "Obsidian + custom indexer" framing | Already verifiable; tightens existing claim. |
| **TV-context (paste TV screenshot → Sonnet vision summary → attention score)** | Mention on About as new pillar, marked "operator surface — not in this demo" | High-signal capability that distinguishes the system; honest framing. |
| **Hypothesis layer + invalidator DSL** | Mention on About as new pillar; explicitly note it's how the "research" tab questions become first-class objects in the live system | Closes the loop on the existing "what it's curious about" card. |
| **Video-vision ingest (Whisper-MLX + Qwen2-VL extracting tickers from YouTube)** | Mention on About as new pillar, operator-only | Apple-Silicon-only, no real demo equivalent. |
| **The Street smart-money tier dashboard** | SKIP — too operator-specific (smart-money brand-name dependency). | Risk-of-overclaim; not core to the demo narrative. |
| **Rx finance prescriptions** | SKIP — operator-only, local-Postgres-only by D-045 lock. | Mentioning it without product would confuse a viewer. |
| **Earnings calendar gating** | Augment existing "Earnings releases inject step-changes" failure-mode card to mention the calendar exists in the system. | Tightens an existing demo claim with real engineering detail. |
| **Macro/sectors regime wheel, rotation bump, correlation heatmap** | Mention on About as new pillar "regime-aware research workbench"; operator surface | Visually rich; honest framing as part of decision-support, not auto-trading. |
| **Ticker review queue (unknown-symbol fan-out from video + tv-context)** | Mention on About as new pillar (operator-only) | Engineering-signal: shows the system handles unknown inputs gracefully. |

## C. Verifiability self-check

Per base CLAUDE.md "Demo-branch verifiability discipline":
- No invented rule names — current demo data uses real labels (`BUY +2% over 5d (HR≥60%)` etc.). ✓
- No precise failure-mode numbers — current copy is qualitative. ✓
- Opt-in / gated behaviour caveated — Research card already says "automatic weekly stress-test loop is gated off by default". ✓
- Separate ingest paths — TV-webhook vs screenshot vs note vs idea vs event will be documented as distinct pipes when surfaced. ✓ (target state)

## D. Disposition summary

- **Phase 2** (prose refresh): A1 + B's "surface" rows.
- **Phase 3** (demo-data): manifest bump, add `system_pillars` array, optional `attention_score` field.
- **Phase 4** (frontend bind): light, no new components beyond a styled list on About.
- **Phase 5** (`.claude/` snapshot): A3 + CHANGELOG.md.
- **NO ACTION** on A4, B's "skip" rows.
