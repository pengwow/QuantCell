"""Ensemble API routes。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.schemas import ApiResponse
from services.ensemble_service import get_ensemble_service
from utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/ensemble", tags=["Ensemble"])


class CreateEnsembleRequest(BaseModel):
    strategy: str = "soft_vote"
    model_paths: list[str] = []


class PredictRequest(BaseModel):
    observation: dict[str, Any] = {}


@router.post(
    "/create",
    summary="创建集成",
    description="model_paths 支持裸 stem(→ MODELS_DIR 下 SB3 zip)或绝对路径(pickle);返回 ensemble_id 与加载失败被跳过的模型明细",
)
async def create_ensemble(req: CreateEnsembleRequest, current_user: dict = Depends(get_current_user)):
    try:
        svc = get_ensemble_service()
        eid, skipped = svc.create_ensemble(strategy=req.strategy, model_paths=req.model_paths)
        return ApiResponse(code=0, message="集成创建成功", data={"ensemble_id": eid, "skipped": skipped})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ensemble_id}/predict")
async def predict(
    ensemble_id: str,
    req: PredictRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        svc = get_ensemble_service()
        result = svc.predict(ensemble_id, req.observation)
        return ApiResponse(code=0, message="预测完成", data=result)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/{ensemble_id}", summary="删除集成", description="删除指定集成,内存与磁盘元数据同步;id 不存在返回 404")
async def delete_ensemble(ensemble_id: str, current_user: dict = Depends(get_current_user)):
    try:
        get_ensemble_service().delete_ensemble(ensemble_id)
        return ApiResponse(code=0, message="集成已删除")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/list")
async def list_ensembles(current_user: dict = Depends(get_current_user)):
    try:
        svc = get_ensemble_service()
        return ApiResponse(code=0, message="success", data=svc.list_ensembles())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
