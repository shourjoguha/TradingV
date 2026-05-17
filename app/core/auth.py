from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import SETTINGS

_api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Security(_api_key_header)) -> str:
    if api_key != SETTINGS.API_KEY:
        raise HTTPException(status_code=403, detail="Bad key")
    return api_key


# Separate header for the rx ingest path (POST /v1/rx/recs). The laptop's
# `/rx-finance` slash command uses a dedicated shared secret instead of
# the operator's primary X-API-Key so the ingest credential can be
# rotated independently — and so a compromised RX_INGEST_TOKEN can't be
# used to read/write the rest of the app. Empty SETTINGS.RX_INGEST_TOKEN
# means ingest is disabled (returns 503 in the dependency).
_rx_ingest_token_header = APIKeyHeader(
    name="X-RX-Ingest-Token", auto_error=False
)


def verify_rx_ingest_token(
    token: str | None = Security(_rx_ingest_token_header),
) -> str:
    if not SETTINGS.RX_INGEST_TOKEN:
        # Fail loud rather than silently accept any token.
        raise HTTPException(
            status_code=503,
            detail="rx ingest disabled: RX_INGEST_TOKEN not configured",
        )
    if not token or token != SETTINGS.RX_INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="Bad rx ingest token")
    return token
