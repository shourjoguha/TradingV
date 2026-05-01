"""GET /v1/views — return the parsed in-memory registry."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import verify_api_key
from app.views import parser

router = APIRouter(prefix="/views", tags=["views"])


@router.get("")
async def list_views(_api_key: str = Depends(verify_api_key)) -> dict:
    return {
        "items": [v.model_dump() for v in parser.REGISTRY.values()],
        "count": len(parser.REGISTRY),
    }


@router.get("/{view_id}")
async def get_view(view_id: str, _api_key: str = Depends(verify_api_key)) -> dict:
    spec = parser.REGISTRY.get(view_id)
    if spec is None:
        from fastapi import HTTPException

        raise HTTPException(404, "view not found")
    return spec.model_dump()
