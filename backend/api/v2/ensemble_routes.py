"""Ensemble API routes。"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from common.schemas import ApiResponse
from services.ensemble_service import get_ensemble_service

router = APIRouter(prefix="/api/v2/ensemble", tags=["Ensemble"])


class CreateEnsembleRequest(BaseModel):
    strategy: str = "soft_vote"
    model_paths: list[str] = []


class PredictRequest(BaseModel):
    observation: dict[str, Any] = {}


@router.post("/create")
async def create_ensemble(req: CreateEnsembleRequest):
    try:
        svc = get_ensemble_service()
        eid = svc.create_ensemble(strategy=req.strategy, model_paths=req.model_paths)
        return ApiResponse(code=0, message="集成创建成功", data={"ensemble_id": eid})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ensemble_id}/predict")
async def predict(ensemble_id: str, req: PredictRequest):
    try:
        svc = get_ensemble_service()
        result = svc.predict(ensemble_id, req.observation)
        return ApiResponse(code=0, message="预测完成", data=result)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/list")
async def list_ensembles():
    try:
        svc = get_ensemble_service()
        return ApiResponse(code=0, message="success", data=svc.list_ensembles())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
