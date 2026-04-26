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


SETTINGS = Settings()
