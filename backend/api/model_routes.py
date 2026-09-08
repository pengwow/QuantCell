"""Model Registry API routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.schemas import ApiResponse
from utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/models", tags=["Models"])


class RegisterModelRequest(BaseModel):
    name: str
    model_path: str
    metadata: dict[str, Any] = {}
    metrics: dict[str, Any] = {}


@router.get("/list")
async def list_models(current_user: dict = Depends(get_current_user)):
    """List all registered models."""
    try:
        from services.model_registry import ModelRegistryService

        svc = ModelRegistryService()
        return ApiResponse(code=0, message="success", data=svc.list_models())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/register")
async def register_model(req: RegisterModelRequest, current_user: dict = Depends(get_current_user)):
    """Register a new model."""
    try:
        from services.model_registry import ModelRegistryService

        svc = ModelRegistryService()
        model_id = svc.register_model(
            name=req.name,
            model_path=req.model_path,
            metadata=req.metadata,
            metrics=req.metrics,
        )
        return ApiResponse(code=0, message="模型注册成功", data={"model_id": model_id})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/{model_id}/promote")
async def promote_model(model_id: str, current_user: dict = Depends(get_current_user)):
    """Promote model to production."""
    try:
        from services.model_registry import ModelRegistryService

        svc = ModelRegistryService()
        success = svc.promote_to_production(model_id)
        return ApiResponse(
            code=0,
            message="晋升成功" if success else "晋升失败",
            data={"success": success},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
