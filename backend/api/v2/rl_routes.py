"""RL Training API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from common.schemas import ApiResponse

router = APIRouter(prefix="/api/v2/rl", tags=["RL Training"])


class TrainRequest(BaseModel):
    algorithm: str = "ppo"
    symbol: str  # 必填：训练目标交易对
    interval: str = "1h"
    candle_type: str = "spot"
    start: str | None = None
    end: str | None = None
    total_timesteps: int = 100000
    reward_type: str = "sharpe"
    walk_forward: bool = False
    wf_splits: int = 5


class WalkForwardRequest(BaseModel):
    symbol: str  # 必填：训练目标交易对
    interval: str = "1h"
    candle_type: str = "spot"
    start: str | None = None
    end: str | None = None
    algorithm: str = "ppo"
    n_splits: int = 5
    mode: str = "rolling"
    total_timesteps: int = 10000
    reward_type: str = "pnl"


@router.post("/train")
async def start_training(req: TrainRequest):
    try:
        from services.rl_service import RLService, RLTrainConfig
        svc = RLService()

        config = RLTrainConfig(
            algorithm=req.algorithm,
            symbol=req.symbol,
            interval=req.interval,
            candle_type=req.candle_type,
            start=req.start,
            end=req.end,
            total_timesteps=req.total_timesteps,
            reward_type=req.reward_type,
            walk_forward=req.walk_forward,
            wf_splits=req.wf_splits,
        )
        result = svc.train(config)
        return ApiResponse(
            code=0,
            message="训练完成",
            data={
                "model_id": result.model_id,
                "status": "completed",
                "metrics": result.metrics,
                "walk_forward": result.walk_forward,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models():
    try:
        from services.model_registry import ModelRegistryService
        svc = ModelRegistryService()
        return ApiResponse(code=0, message="success", data=svc.list_models())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/walk-forward")
async def run_walk_forward(req: WalkForwardRequest):
    try:
        from services.rl_service import RLService, RLTrainConfig
        svc = RLService()

        config = RLTrainConfig(
            algorithm=req.algorithm,
            symbol=req.symbol,
            interval=req.interval,
            candle_type=req.candle_type,
            start=req.start,
            end=req.end,
            total_timesteps=req.total_timesteps,
            reward_type=req.reward_type,
            walk_forward=True,
            wf_splits=req.n_splits,
        )
        result = svc.train(config)
        return ApiResponse(
            code=0,
            message="Walk-Forward 验证完成",
            data={"walk_forward": result.walk_forward, "model_id": result.model_id},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hpo")
async def run_hpo():
    raise HTTPException(status_code=501, detail="HPO not yet implemented")
