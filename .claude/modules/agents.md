# Agents lane (TradingAgents)

A second, independent decision engine that runs **side-by-side with Kronos**, never replacing it. Where Kronos forecasts a price path that the rule engine turns into opportunities, the Agents lane runs a multi-agent LLM "trading firm" ([TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents), Apache-2.0) that debates a ticker and emits a discrete **BUY / SELL / HOLD** decision with a rationale. The two lanes do not depend on or talk to each other.

Ships dark: nothing runs unless `AGENTS_ENABLED=true` (mirrors the Kronos `KRONOS_ENABLED` optional-engine pattern).

## Why a separate lane (and no opportunities bridge)

`opportunities` is NOT-NULL FK-bound to Kronos' `prediction_points` — an agent decision has no valid prediction row to point at. Rather than mutate that shared schema, the Agents lane keeps its own `agent_decisions` table and its own `/v1/agents/decisions` surface. This honors the "additive, side-by-side, need not talk" constraint without perturbing the Kronos path.

## Schema

`agent_decisions` (migration `0032`):
```
id PK,
ticker, made_on (date),
engine DEFAULT 'tradingagents', engine_version,
stance ('BUY'|'SELL'|'HOLD'),
confidence (0..1, nullable),
rationale_md, transcript_ref, meta (JSON),
created_at,
UNIQUE(ticker, made_on, engine_version)   -- idempotent daily re-run
```

## Layout (mirrors app/kronos)

- `adapter.py` — `AgentDecision` dataclass + `AgentEngine` Protocol + `StubAgentEngine`. The stub refuses to fabricate decisions unless `DEBUG_STUB=true` (then deterministic). `get_engine()` / `set_engine()` are the swap points; the rest of the app only ever sees `AgentDecision`.
- `real_engine.py` — lazy wrapper over TradingAgents (heavy deps in `requirements-agents.txt`, imported only inside `decide`). `activate()` swaps the stub at boot when `AGENTS_ENABLED`. Reuses `CLAUDE_MODEL` and respects the admin Anthropic kill-switch.
- `service.py` — `run_for_ticker` (idempotent upsert), `run_for_watchlist` (best-effort per ticker), `list_decisions`.
- `routes.py` — `GET /v1/agents/engine`, `GET /v1/agents/decisions`, `POST /v1/agents/run` (one ticker or whole watchlist; 422 when the engine isn't wired, 409 on kill-switch).

## Scheduling

`app/main.py` lifespan spawns a daily `agents-tick` loop **only** when `AGENTS_ENABLED` (laptop-only, post-boot warmup). Registered in the admin loop registry (`app/admin/loops.py`) as `agents` — cost-sensitive, confirm-modal, default off.

## Enabling in production

1. `pip install -r requirements-agents.txt`
2. Set `AGENTS_ENABLED=true` (+ `CLAUDE_MODEL` / Anthropic key, optional `AGENTS_DEEP_MODEL` / `AGENTS_QUICK_MODEL`).
3. `alembic upgrade head` (applies `0032`).

## Operator review flow (any ticker list, no watchlist needed)

The lane only exposed `run_for_ticker` + `POST /v1/agents/run`. `scripts/agents_review.py`
is the reusable CLI on top of it: run the debate over an arbitrary ticker list, augment each
decision into a structured **6–12mo downside/upside** (`app/agents/review.py`, stored on
`agent_decisions.meta["review"]` — no schema change), and snapshot to JSON.
`scripts/agents_report.py` renders that snapshot into a committed markdown report + a
self-contained, theme-aware HTML dashboard (publishable as an Artifact).

No docker required — the lane runs over SQLite too. See `.env.laptop.example`.

```bash
export DATABASE_URL="sqlite+aiosqlite:///./dev.db"    # or your Postgres URL
pip install -r requirements.txt -r requirements-agents.txt
export AGENTS_ENABLED=true ANTHROPIC_API_KEY=... FINNHUB_API_KEY=...
alembic upgrade head
python scripts/agents_review.py MSFT PYPL NFLX NOW GOOGL MSTR \
    --out reports/agents-review-$(date +%F).json
python scripts/agents_report.py --from reports/agents-review-$(date +%F).json \
    --md reports/agents-review-$(date +%F).md --html reports/agents-review-$(date +%F).html
```

With the lane disabled the review CLI refuses to emit meaningless stub verdicts unless
`DEBUG_STUB=1` (which produces deterministic synthetic decisions for pipeline testing only —
the report banners them loudly as NOT real analysis).

## Tests

`tests/test_agents.py` drives the stub end-to-end: engine info, run-without-engine → 422, idempotent upsert, watchlist run, and a guard that the lane writes nothing to the opportunities feed.
