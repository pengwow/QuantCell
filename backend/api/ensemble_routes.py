"""Ensemble API routes。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.schemas import ApiResponse
from services.ensemble_service import get_ensemble_service
from services.rl_service import RLService
from utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/ensemble", tags=["Ensemble"])


class CreateEnsembleRequest(BaseModel):
    strategy: str = "soft_vote"
    model_paths: list[str] = []


class PredictRequest(BaseModel):
    observation: dict[str, Any] = {}


class EnsembleBacktestRequest(BaseModel):
    symbol: str
    interval: str = "1h"
    initial_capital: float = 100_000.0


@router.post(
    "/{ensemble_id}/backtest",
    summary="集成回测",
    description="集成成员均值聚合跑统一内核回测(engine=kernel,集成仅该引擎支持);"
    "按 symbol/interval 拉历史K线,返回 PnL/Sharpe/最大回撤/胜率等指标;"
    "集成不存在或数据不可得时 400",
)
async def backtest_ensemble(
    ensemble_id: str,
    req: EnsembleBacktestRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        # 集成模式下 run_backtest 忽略 model_path;engine 必须显式 kernel
        # (默认 trading_env 会被"集成仅 kernel"校验拒绝,报错语义绕)
        result = RLService().run_backtest(
            model_path="",
            symbol=req.symbol,
            interval=req.interval,
            initial_capital=req.initial_capital,
            engine="kernel",
            ensemble_id=ensemble_id,
        )
        return ApiResponse(code=0, message="回测完成", data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


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
    except ValueError as e:
        # 非空观测缺特征:服务层严校转 400(零观测冒烟走不到这里)
        raise HTTPException(status_code=400, detail=str(e))
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
