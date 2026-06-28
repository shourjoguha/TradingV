from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    API_KEY: str
    PORT: int = 8000
    # When true, the Kronos stub returns a deterministic synthetic forecast
    # instead of raising NotImplementedError. For local dev / Phase 4 tests
    # of the orchestrator shape. MUST be false in any real deployment.
    DEBUG_STUB: bool = False
    # When true, replace the stub Kronos adapter with the real one at
    # startup. Requires the extras in requirements-kronos.txt to be
    # installed on the host (torch, huggingface_hub, etc).
    KRONOS_ENABLED: bool = False

    # Agents lane (TradingAgents) — runs SIDE BY SIDE with Kronos, never
    # replacing it. When true, the stub engine is swapped for the real
    # multi-agent engine at startup (requires requirements-agents.txt) and a
    # daily decision loop runs over the watchlist. Default False: ships dark.
    AGENTS_ENABLED: bool = False
    # Daily agents loop cadence (seconds) and post-boot warmup.
    AGENTS_SLEEP_SECONDS: int = 86400
    AGENTS_WARMUP_SECONDS: int = 1800
    # Optional LLM overrides for the agents engine. Empty => reuse CLAUDE_MODEL.
    AGENTS_LLM_PROVIDER: str = "anthropic"
    AGENTS_DEEP_MODEL: str = ""
    AGENTS_QUICK_MODEL: str = ""

    # Data-source API keys (all optional; a provider/feed self-disables when
    # its key is empty). Surfaced via GET /v1/api-list as `configured` flags.
    ALPHAVANTAGE_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    # When true, register the Alpha Vantage OHLCV provider at boot (appended
    # after yfinance, which stays primary). No-op unless a key is also set.
    ALPHAVANTAGE_PROVIDER_ENABLED: bool = False
    # Dual-backend deployment:
    # - INSTANCE_NAME is informational ("laptop" | "railway"), surfaced in
    #   /health + logs so we know which replica responded.
    # - PEER_API_URL + PEER_API_KEY point at the OTHER backend. When set,
    #   finished jobs enqueue a ticker-sync to that peer.
    # - MAX_CONCURRENT_JOBS gates /v1/analysis/run. Exceeding returns 429.
    INSTANCE_NAME: str = "local"
    PEER_API_URL: str = ""
    PEER_API_KEY: str = ""
    MAX_CONCURRENT_JOBS: int = 1
    # CORS allow-list. Comma-separated absolute origins
    # ("https://your-app.lovable.dev,https://app.example.com"). Empty
    # falls back to the local-dev defaults below.
    FRONTEND_ORIGIN: str = ""
    # Railway-fallback inference: when enabled AND INSTANCE_NAME='railway',
    # the schedule runner spawns a second loop that fires submit_run() if
    # the laptop hasn't pushed today's predictions by run_at_local +
    # fallback_offset_hours. Off by default — explicit opt-in.
    RAILWAY_FALLBACK_ENABLED: bool = False
    # Days to keep completed sync_outbox rows. Hourly purge in lifespan.
    OUTBOX_RETENTION_DAYS: int = 7
    # Telegram bot for drift alerts + daily digest. Both must be set or the
    # notifier no-ops gracefully (logged once per send attempt). Get token
    # from @BotFather, chat_id from a quick getUpdates call after DM-ing
    # your bot.
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    # Drift detection: recent_window_mape must exceed all_time_mape * this
    # ratio to flag (with min sample sizes). Tunable via env once we have
    # real data to calibrate against.
    DRIFT_RATIO_THRESHOLD: float = 1.5
    DRIFT_MIN_RECENT_SAMPLES: int = 10
    DRIFT_MIN_ALL_TIME_SAMPLES: int = 30
    DRIFT_RECENT_WINDOW_DAYS: int = 30
    # Daily digest UTC hour (0-23). 12 = 12:00 UTC ≈ 8 AM ET.
    DIGEST_HOUR_UTC: int = 12
    # TV-context retention defaults (days). Per-row override at ingest.
    TV_CTX_RETENTION_WEBHOOK_DAYS: int = 7
    TV_CTX_RETENTION_SCREENSHOT_DAYS: int = 30
    TV_CTX_RETENTION_NOTE_DAYS: int = 180
    TV_CTX_RETENTION_IDEA_DAYS: int = 180
    # Events expire `event_date + N days` (post-event window).
    TV_CTX_RETENTION_EVENT_POST_DAYS: int = 30
    # Webhook dedupe rolling window (seconds). Spammy Pine alerts (RSI hovering)
    # collapse into a single row with payload.dedupe_count incremented.
    TV_CTX_WEBHOOK_DEDUPE_WINDOW_SEC: int = 60
    # Vision summarization on screenshot ingest. Default ON per operator
    # preference (low typing-effort > marginal $/image cost).
    TV_CTX_SCREENSHOT_VISION_DEFAULT: bool = True
    TV_CTX_VISION_MODEL: str = "claude-sonnet-4-6"
    TV_CTX_VISION_MAX_WIDTH_PX: int = 1024
    # Ticker-review parity: when an operator submits a TV-context input
    # with a ticker NOT in the operator's universe (roster ∪ boards ∪
    # The Street), enqueue it to ticker_review_queue. Default ON in prod.
    # Tests disable to keep ingest path side-effect-free at the SQLite
    # serial-write lock boundary.
    TV_CTX_TICKER_REVIEW_ENABLED: bool = True
    # tv_context expire-sweep interval (seconds). Laptop runs every 12h;
    # Railway runs daily by default to reduce serverless wake-ups.
    # (Reduced 2026-05-16 from hourly per operator request — Railway shut.)
    TV_CTX_EXPIRE_INTERVAL_SECONDS: int = 43200
    # Outbox drain cadence (seconds). Replaces per-analysis-job drain to
    # batch sync pushes — one wake-up every N seconds instead of one per
    # completed job. Laptop-only loop; Railway never drains (it's a
    # passive replica, has nothing to push).
    # Honoured only when SYNC_ENABLED=true AND peer credentials are set.
    SYNC_DRAIN_INTERVAL_SECONDS: int = 300
    # Master kill-switch for laptop→peer sync. Default False since Railway
    # is shut as of 2026-05-16; set True (+ peer creds) to re-enable.
    SYNC_ENABLED: bool = False

    # Video channel auto-ingest (per `_channel.yaml`). Off by default so
    # existing vaults aren't surprised on next deploy; flip to true when
    # the operator has authored a `_channel.yaml` and wants the loop to
    # start polling. Laptop-only — vault lives on the operator's disk.
    VIDEO_INGEST_ENABLED: bool = False
    VIDEO_INGEST_WARMUP_SECONDS: int = 3600                  # 1 hr post-boot
    # Daily — operator request 2026-05-16; per-channel cadence still respected via _channel.yaml.last_polled_at
    VIDEO_INGEST_SLEEP_SECONDS: int = 86400

    # SEC EDGAR auto-ingest. Polls every roster ticker for new 8-K / 10-Q /
    # 10-K filings on the configured cadence. Off by default; opt-in once
    # the operator has set EDGAR_USER_AGENT (required by SEC). Laptop-only
    # via `if not is_railway` gate.
    EDGAR_INGEST_ENABLED: bool = False
    EDGAR_INGEST_WARMUP_SECONDS: int = 3600                  # 1 hr post-boot
    # Weekly — operator request 2026-05-16; reduced from 6h since filings cluster around earnings windows and weekly cadence catches them while costing less.
    EDGAR_INGEST_SLEEP_SECONDS: int = 604800
    EDGAR_INGEST_FORM_TYPES: str = "8-K,10-Q,10-K"           # comma-separated
    EDGAR_INGEST_MAX_PER_FORM: int = 3                       # cap per ticker per tick

    # rx (prescription) layer — finance recs only. Per D-045
    # (Sho's Playgroun/rx-meta/DECISIONS-LOG.md), TradingV is the
    # exclusive host for finance recs. Lovable/Supabase handles fitness +
    # nutrition.
    # - RX_OPERATOR_UUID: stamped on every rec row server-side. Default
    #   matches Lovable's single-tenant operator so any future RLS-style
    #   filtering stays consistent across both backends.
    # - RX_INGEST_TOKEN: shared secret for POST /v1/rx/recs from the
    #   laptop's `/rx-finance` slash command. NEVER log this value.
    #   Empty default disables ingest (returns 503) so a missing env var
    #   fails loud instead of accepting unauthenticated writes.
    RX_OPERATOR_UUID: str = "9312c7a0-d09c-4663-8f67-5dfddfdb6249"
    RX_INGEST_TOKEN: str = ""

    # Auto-add ticker to a board on buy-trade log. Default "positions"
    # matches the seeded board from the 2026-05-17 positions_ledger
    # import. Empty string disables the fan-out entirely. Buy-only
    # (sells often close a position; auto-add on sell would be wrong).
    # Lookup is case-insensitive against `boards.name`. Best-effort:
    # board-missing or any failure is logged + swallowed, never blocks
    # the trade write.
    TRADES_AUTOADD_BOARD_NAME: str = "positions"


SETTINGS = Settings()
