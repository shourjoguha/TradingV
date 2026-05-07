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
    # tv_context expire-sweep interval (seconds). Laptop runs hourly;
    # Railway runs daily by default to reduce serverless wake-ups.
    TV_CTX_EXPIRE_INTERVAL_SECONDS: int = 3600
    # Outbox drain cadence (seconds). Replaces per-analysis-job drain to
    # batch sync pushes — one wake-up every N seconds instead of one per
    # completed job. Laptop-only loop; Railway never drains (it's a
    # passive replica, has nothing to push).
    SYNC_DRAIN_INTERVAL_SECONDS: int = 300

    # Video channel auto-ingest (per `_channel.yaml`). Off by default so
    # existing vaults aren't surprised on next deploy; flip to true when
    # the operator has authored a `_channel.yaml` and wants the loop to
    # start polling. Laptop-only — vault lives on the operator's disk.
    VIDEO_INGEST_ENABLED: bool = False
    VIDEO_INGEST_WARMUP_SECONDS: int = 3600                  # 1 hr post-boot
    VIDEO_INGEST_SLEEP_SECONDS: int = 3600                   # check hourly; per-channel cadence respected via _channel.yaml.last_polled_at


SETTINGS = Settings()
