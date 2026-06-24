"""Risk Monitor API routes."""

import math
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

router = APIRouter(prefix="/api/v2/risk", tags=["Risk"])


def _sanitize(obj: Any) -> Any:
    """Replace inf/nan with None for JSON compliance."""
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


class CheckOrderRequest(BaseModel):
    order: dict[str, Any]
    portfolio: dict[str, Any]


@router.post("/check")
async def check_order(req: CheckOrderRequest):
    try:
        from services.risk_service import RiskService
        svc = RiskService()
        return svc.check_order(req.order, req.portfolio)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/metrics")
async def get_metrics():
    try:
        from services.risk_service import RiskService
        svc = RiskService()
        return _sanitize(svc.get_metrics())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/reset")
async def reset_daily():
    try:
        from services.risk_service import RiskService
        svc = RiskService()
        svc.reset_daily()
        return {"status": "ok"}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
