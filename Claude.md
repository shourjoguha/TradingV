# TradingView Analysis Platform

## What this is (60 seconds)

Personal trading-decision-support system for **one operator**. FastAPI backend runs Kronos candlestick predictions on a daily-scheduled watchlist; emits **opportunities** (rule-based BUY/SELL signals weighted by historical hit-rate); manually-logged **trades** close the loop with per-rule P\&L attribution. Bidirectional Tailscale sync between **laptop** (primary, has GPU-eligible inference) and **Railway** (always-on replica). Neumorphic React frontend on **Cloudflare Pages** at `https://tradingv-83b.pages.dev`. **Read** **[.claude/principles.md](.claude/guides/principles.md)** **before making architectural changes** — it captures the load-bearing assumptions and trade-offs.

## Reading paths (start here based on your job)

| Job                 | Read in this order                                                                                                                             |
| :------------------ | :--------------------------------------------------------------------------------------------------------------------------------------------- |
| Onboarding fresh    | [principles.md](.claude/guides/principles.md) → [architecture.md](.claude/guides/architecture.md) → [roadmap-shipped.md](.claude/status/roadmap-shipped.md)         |
| Adding a feature    | [recipes.md](.claude/guides/recipes.md) → the relevant module doc → [architecture.md](.claude/guides/architecture.md)                                        |
| Fixing a prod bug   | [railway-deployment.md](.claude/guides/railway-deployment.md) → the module → [backlog.md](.claude/status/backlog.md) + [tech\_debt.md](.claude/status/tech_debt.md) |
| Auditing a decision | [decisions/](.claude/decisions/) (ADRs) → [backlog.md](.claude/status/backlog.md) (RESOLVED entries)                                                  |
| Frontend only       | [frontend/README.md](.claude/frontend/README.md)                                                                                               |
| Adding a UI control | [frontend/ui-components.md § Compositions](.claude/frontend/ui-components.md) — pick the canonical pattern (page tab vs filter chip) BEFORE rolling new buttons |
| Defining a term     | [glossary.md](.claude/guides/glossary.md)                                                                                                             |
| Driving app from Claude Desktop | [research-from-claude-desktop.md](.claude/guides/research-from-claude-desktop.md) — endpoint catalogue + workflow recipes for subscription-billed research sessions from Claude Desktop |

## Entry points

- App: `app.main:app`
- Local: `uvicorn app.main:app --reload` (venv activated, env set)
- Deploy: Railway via Dockerfile + `tailscale-entrypoint.sh`. `railway.toml` declares the Dockerfile builder; the entrypoint runs Tailscale, then chains `alembic upgrade head && uvicorn ...` from the Dockerfile CMD. `Procfile` is unused on Railway. See [.claude/railway-deployment.md](.claude/guides/railway-deployment.md).
- **Vault-indexer (Phase 2/3 knowledge layer)**: `uvicorn tools.vault_indexer.app:app --port 8001` with `VAULT_PATH=$HOME/Documents/knowledge-vault`. **Multi-domain vault**: the same vault now hosts a fitness indexer on `:8002` with its own cache. The finance indexer (`:8001`) **MUST** launch with `EXCLUDE_FOLDERS=Videos/fitness,Topics/fitness,Newsletters/fitness,Books/fitness` or `/search` surfaces fitness chunks. `run-dev.sh` injects this default. Full multi-domain rules in [`tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md`](tools/vault_indexer/MULTI_DOMAIN_BRIEFING.md). Required for `/v1/research/ask`. **The cache at `<vault>/.indexer/cache.db` persists across restarts** — laptop reboots don't trigger re-embedding. Full operator runbook in [`use_me_guide.md`](use_me_guide.md) §1.5.

## `.claude/` — folder-first reference

The docs are grouped into themed folders. **Always read the folder README first** — it points at the right file inside. This indirection keeps CLAUDE.md stable as individual docs come and go.

| Concern | Folder | What's inside (see folder README for the full index) |
| :--- | :--- | :--- |
| Touching a specific `app/<module>/` | [.claude/modules/](.claude/modules/README.md) | One file per app module: `accuracy.md`, `admin.md`, `analysis.md`, `boards.md`, `core.md`, `earnings.md`, `hypotheses.md`, `kronos.md`, `labels.md`, `macro.md`, `market_data.md`, `notifications.md`, `opportunities.md`, `predictions.md`, `queue.md`, `research.md`, `schedule.md`, `sync.md`, `tickers.md`, `trades.md`, `ticker_review.md`, `tv_context.md`, `vault.md`, `video_vision.md`, `views.md`, `watchlist.md`, `alerts.md` |
| Cross-cutting how-to (architecture, principles, setup, deploy, testing, migrations, recipes, glossary) | [.claude/guides/](.claude/guides/README.md) | `architecture.md` (system map — start here), `principles.md`, `glossary.md`, `recipes.md`, `testing.md`, `migrations.md`, `railway-deployment.md`, `laptop-setup.md` |
| What's queued / shipped / deferred / known-broken | [.claude/status/](.claude/status/README.md) | `roadmap.md`, `roadmap-shipped.md`, `backlog.md`, `tech_debt.md` |
| Why we made a binding tradeoff (ADRs) | [.claude/decisions/](.claude/decisions/README.md) | Numbered ADRs `001-…` through latest |
| Detailed phase plans (authored before execution) | [.claude/plans/](.claude/plans/README.md) | One markdown per phase plan; brainstorms / pre-plans live here too |
| Periodic architecture / pattern reviews | [.claude/reviews/](.claude/reviews/README.md) | Date-stamped point-in-time reviews |
| Operator-authored hypothesis drafts | [.claude/hypotheses/](.claude/hypotheses/README.md) | Markdown sources for each hypothesis (DB-derived) |
| Frontend-specific docs | [.claude/frontend/](.claude/frontend/README.md) | Pages, hooks, API client, UI compositions, design system |
| Stale handoffs (context-audit only) | [.claude/archive/](.claude/archive/README.md) | Superseded session-handoff snapshots |

**Reading protocol:** pick the folder from the table above, open its README to find the specific file, then read that file. The folder README always lists every file inside with a one-line "what / when to read" annotation.

When in doubt, [.claude/guides/architecture.md](.claude/guides/architecture.md) has the system map.

## Setup (local)

1. `python3 -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. Export `DATABASE_URL` (Postgres or `sqlite+aiosqlite:///./dev.db`) and `API_KEY`.
4. `alembic upgrade head` (or rely on `create_all` in the lifespan for first boot).
5. `uvicorn app.main:app --reload`
6. Tests: `python -m pytest`.

**Video-vision deps** (optional; Apple Silicon recommended): `brew install tesseract` for the OCR layer. The `mlx-whisper` + `mlx-vlm` Python wheels come via `requirements.txt`; they're no-op on non-Apple-Silicon (adapter falls back to torch). First L3 ingest tick auto-downloads ~1.5GB of model weights (Whisper-MLX + Qwen2-VL-2B-4bit) to `~/.cache/huggingface/`. See [.claude/modules/video_vision.md](.claude/modules/video_vision.md).

For the **laptop (primary) backend** with dockerized Postgres on 5439 + peer sync to Railway, see [.claude/laptop-setup.md](.claude/guides/laptop-setup.md).

## Setup (Railway)

1. New project → add Postgres plugin → deploy repo. Builder: Dockerfile (declared in `railway.toml`).
2. Set `API_KEY` env var. `DATABASE_URL`/`PORT` are auto-injected.
3. Alembic runs at container start (entrypoint chains `alembic upgrade head && uvicorn ...`).
4. Optional: `TS_AUTHKEY` for Tailscale tunnel back to laptop, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` for push alerts (both no-op when unset). Full env list in [.claude/railway-deployment.md](.claude/guides/railway-deployment.md).

## Demo-branch verifiability discipline

The `demo` branch is the public face on Cloudflare Pages. **Every numeric claim, named feature, or capability description on demo must trace to something that actually ships in `main`.** Specifically:

- **No invented rule names / strategy names.** Use the real rule labels (`rule_label` field in `app/opportunities/rules.py`, e.g. `"BUY +2% over 5d (HR≥60%)"`).
- **No precise failure-mode numbers** (e.g. "~12pt drop", "~2× MAPE", "~6pt cohort delta") unless a query in `scripts/bake_demo_snapshot.py` computes that exact number from the live DB. Otherwise: soften to a qualitative statement.
- **No claims of automatic behaviour that's actually opt-in or gated** (e.g. weekly research stress-test, Telegram alerts). When the live path is conditional, the demo copy must say "(when configured)" or similar.
- **No conflation of separate ingest paths.** TradingView webhooks carry text alerts; chart screenshots arrive via operator paste — these are two pipes, document them as such.

When in doubt, trim. Audit precedent: `.claude/plans/ok-now-we-have-distributed-anchor.md` "Demo Branch Claims Audit" section + the 2026-05-12 retro in [.claude/status/roadmap-shipped.md](.claude/status/roadmap-shipped.md).

## Local knowledge base catalog (auto-loaded)
@~/.claude/kb-overview.md
