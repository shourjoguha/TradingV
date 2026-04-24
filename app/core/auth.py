from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import SETTINGS

_api_key_header = APIKeyHeader(name="X-API-Key")


def verify_api_key(api_key: str = Security(_api_key_header)) -> str:
    if api_key != SETTINGS.API_KEY:
        raise HTTPException(status_code=403, detail="Bad key")
    return api_key
