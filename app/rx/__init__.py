"""rx — prescription layer surface (finance only on TradingV).

TradingV is the exclusive host for finance recommendations per D-045
(Sho's Playgroun/rx-meta/DECISIONS-LOG.md). Fitness + nutrition recs live
in Lovable/Supabase and never touch this module.

Generation lives on the laptop (Claude Code `/rx-finance` slash command).
TradingV ingests via POST /v1/rx/recs (X-RX-Ingest-Token auth) and
exposes read/disposition endpoints under /v1/rx/recs/*.
"""
