# Handover — fresh-session entry point

> Full context dump lives at:
> `~/.claude/projects/-Users-shourjosmac-Documents-Claude-TradingView-/memory/handover-2026-05-08.md`

## TL;DR for next Claude session

Across 2026-05-04 → 2026-05-08, in this project:

1. **TV Context layer (Phases 1-6)** shipped — `app/tv_context/` module + frontend `/tv-context/:ticker?` page. Webhook fan-out + manual screenshots + vision auto-summary + research-ask gating + trade-close enrichment. UI gated to laptop backend only.
2. **Railway cost cut** — gated 9 background loops by `INSTANCE_NAME != 'railway'` + batched outbox drain. Operator must set `INSTANCE_NAME=railway` on Railway to fire the gate. Expected $25→$5-8/mo.
3. **Video ASR Canary-Qwen rollback** — tried, failed on 16GB M3, fully removed (~6GB disk reclaimed). Whisper stays default.
4. **YouTube channel poller fixes** — wired `auto_promote: true` (was no-op), added Shorts filter, new `cleanup_shorts.py` CLI. `fx-evolution-daily` cleaned: 3 Shorts removed, 2 long-forms promoted.
5. **Gekko Smart Money scrape** — see this folder. 186 multi-channel tickers, 4 Tier-1 (META, TSM, MU, GOOGL).

## Where things live

- **TV Context module**: `app/tv_context/`
- **Channel auto-ingest**: `tools/vault_indexer/ingest/youtube_channel.py`
- **Shorts cleanup**: `tools/vault_indexer/cleanup_shorts.py`
- **Lifespan gating**: `app/main.py:lifespan` (search `is_railway`)
- **Tech debt list**: `.claude/tech_debt.md`
- **Module doc**: `.claude/tv_context.md`
- **ADRs**: `.claude/decisions/016`, `017`
- **Gekko outputs**: `gekko-insights/<date>/{raw,aggregate,notes.md}`

## Operator state

- **Caveman mode active** across sessions (drop articles, fragments OK)
- **Auto mode** on/off varies — defaults to off; user explicit when on
- **Plan mode** off by default
- Claude-for-Chrome extension ≠ Claude Code MCP. Playwright MCP is installed (`claude mcp list` shows it)

## Pending actions on operator side

- Set `INSTANCE_NAME=railway` on Railway dashboard
- Bounce Railway service to pick up lifespan gate
- Watch bill 1 week post-deploy

## Test state at handover

- Backend: 394 pass
- Frontend: TS clean
- Pre-existing skip: `tests/test_vault_indexer.py` (unrelated transformers/hf_hub mismatch)
