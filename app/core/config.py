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


SETTINGS = Settings()
