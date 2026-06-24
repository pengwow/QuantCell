"""Model Registry API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

router = APIRouter(prefix="/api/v2/models", tags=["Models"])


class RegisterModelRequest(BaseModel):
    name: str
    model_path: str
    metadata: dict[str, Any] = {}
    metrics: dict[str, Any] = {}


@router.get("/list")
async def list_models():
    """List all registered models."""
    try:
        from services.model_registry import ModelRegistryService
        svc = ModelRegistryService()
        return svc.list_models()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/register")
async def register_model(req: RegisterModelRequest):
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
        return {"model_id": model_id}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/{model_id}/promote")
async def promote_model(model_id: str):
    """Promote model to production."""
    try:
        from services.model_registry import ModelRegistryService
        svc = ModelRegistryService()
        success = svc.promote_to_production(model_id)
        return {"success": success}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
