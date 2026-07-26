"""Model Registry API routes."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any
from common.schemas import ApiResponse
from utils.auth import jwt_auth_required

router = APIRouter(prefix="/api/v2/models", tags=["Models"])


class RegisterModelRequest(BaseModel):
    name: str
    model_path: str
    metadata: dict[str, Any] = {}
    metrics: dict[str, Any] = {}


@router.get("/list")
@jwt_auth_required
async def list_models(request: Request):
    """List all registered models."""
    try:
        from services.model_registry import ModelRegistryService
        svc = ModelRegistryService()
        return ApiResponse(code=0, message="success", data=svc.list_models())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/register")
@jwt_auth_required
async def register_model(request: Request, req: RegisterModelRequest):
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
@jwt_auth_required
async def promote_model(request: Request, model_id: str):
    """Promote model to production."""
    try:
        from services.model_registry import ModelRegistryService
        svc = ModelRegistryService()
        success = svc.promote_to_production(model_id)
        return ApiResponse(code=0, message="晋升成功" if success else "晋升失败", data={"success": success})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
