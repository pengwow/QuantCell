"""RL Training API routes."""

import functools

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from common.schemas import ApiResponse
from utils.auth import jwt_auth_required

router = APIRouter(prefix="/api/v2/rl", tags=["RL Training"])


def _map_rl_exception(exc: Exception) -> HTTPException:
    """将 RL service 层异常映射为语义化 HTTP 状态码。

    - ValueError: 参数/配置错误 → 400
    - RuntimeError: 依赖缺失（axon_quant / stable-baselines3 未安装）→ 503
    - 其余: 内部错误 → 500
    """
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def handle_rl_exceptions(func):
    """RL 端点统一异常处理：消除各端点重复的 try/except。"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            raise _map_rl_exception(exc) from exc

    return wrapper


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
@jwt_auth_required
@handle_rl_exceptions
async def start_training(request: Request, req: TrainRequest):
    # 延迟导入：避免 API 启动时加载 stable-baselines3/torch 等训练重依赖
    from services.rl_service import RLService, RLTrainConfig

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
    result = RLService().train(config)
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


@router.get("/models")
@jwt_auth_required
@handle_rl_exceptions
async def list_models(request: Request):
    # 延迟导入：ModelRegistryService 依赖 axon_quant.registry
    from services.model_registry import ModelRegistryService

    return ApiResponse(code=0, message="success", data=ModelRegistryService().list_models())


@router.post("/walk-forward")
@jwt_auth_required
@handle_rl_exceptions
async def run_walk_forward(request: Request, req: WalkForwardRequest):
    # 延迟导入：避免 API 启动时加载 stable-baselines3/torch 等训练重依赖
    from services.rl_service import RLService, RLTrainConfig

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
    result = RLService().train(config)
    return ApiResponse(
        code=0,
        message="Walk-Forward 验证完成",
        data={"walk_forward": result.walk_forward, "model_id": result.model_id},
    )
