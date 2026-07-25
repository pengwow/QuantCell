"""Risk Monitor API routes."""

import math
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from common.schemas import ApiResponse

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


@lru_cache(maxsize=1)
def _get_risk_service():
    """模块级单例，避免每次请求重置风控引擎计数器。"""
    from services.risk_service import RiskService
    return RiskService()


class CheckOrderRequest(BaseModel):
    order: dict[str, Any]
    portfolio: dict[str, Any]


@router.post("/check")
async def check_order(req: CheckOrderRequest):
    try:
        svc = _get_risk_service()
        result = svc.check_order(req.order, req.portfolio)
        return ApiResponse(code=0, message="风控检查完成", data=result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/metrics")
async def get_metrics():
    try:
        svc = _get_risk_service()
        return ApiResponse(code=0, message="success", data=_sanitize(svc.get_metrics()))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/reset")
async def reset_daily():
    try:
        svc = _get_risk_service()
        svc.reset_daily()
        return ApiResponse(code=0, message="每日计数已重置", data={"status": "ok"})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
