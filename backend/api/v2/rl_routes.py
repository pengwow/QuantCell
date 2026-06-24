"""RL Training API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/rl", tags=["RL Training"])


class TrainRequest(BaseModel):
    algorithm: str = "ppo"
    data_source: str = "BTCUSDT_1h"
    total_timesteps: int = 100000
    reward_type: str = "sharpe"
    walk_forward: bool = False
    hpo: bool = False


@router.post("/train")
async def start_training(req: TrainRequest):
    try:
        from services.rl_service import RLService, RLTrainConfig
        svc = RLService()
        config = RLTrainConfig(
            algorithm=req.algorithm,
            total_timesteps=req.total_timesteps,
            reward_type=req.reward_type,
            walk_forward=req.walk_forward,
        )
        result = svc.train(config)
        return {"model_id": result.model_id, "status": "completed", "metrics": result.metrics}
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
        return svc.list_models()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/walk-forward")
async def run_walk_forward():
    raise HTTPException(status_code=501, detail="Walk-Forward not yet implemented")


@router.post("/hpo")
async def run_hpo():
    raise HTTPException(status_code=501, detail="HPO not yet implemented")
