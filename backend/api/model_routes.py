"""Model Registry API routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
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


@router.get("/{model_id}/detail", summary="模型详情")
async def get_model_detail(model_id: str, current_user: dict = Depends(get_current_user)):
    """查询模型详情(名称/版本/指标/文件信息);未晋升模型走 get_latest 兜底,仅查无此名返回 404。"""
    try:
        from services.model_registry import ModelRegistryService

        svc = ModelRegistryService()
        detail = svc.get_model_detail(model_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="模型不存在")
        return ApiResponse(code=0, message="success", data=detail)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/{model_id}/download", summary="下载模型文件")
async def download_model(model_id: str):
    """下载 production 模型 artifact。

    ponytail: 不走 Authorization 头(浏览器 <a download> 无法附带 JWT)、
    无大小/速率限制——内网单机假设;升级路径为签名 URL 或 limiter。
    """
    try:
        from services.model_registry import ModelRegistryService

        svc = ModelRegistryService()
        path = svc.get_artifact_path(model_id)
        if path is None:
            raise HTTPException(status_code=404, detail="模型文件不存在或无生产版本")
        return FileResponse(path, filename=f"{model_id}.zip")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
