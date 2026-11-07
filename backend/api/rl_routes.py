"""RL Training API routes."""

import functools

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.schemas import ApiResponse
from utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/rl", tags=["RL Training"])


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
@handle_rl_exceptions
async def start_training(req: TrainRequest, current_user: dict = Depends(get_current_user)):
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
@handle_rl_exceptions
async def list_models(current_user: dict = Depends(get_current_user)):
    """列出已训练模型（数据源为 data/models 下真实 .zip 文件，含大小/路径/时间）。"""
    # 延迟导入：避免 API 启动时加载 stable-baselines3/torch 等训练重依赖
    from services.rl_service import RLService

    return ApiResponse(code=0, message="success", data=RLService().list_saved_models())


@router.delete("/models/{model_id}")
@handle_rl_exceptions
async def delete_model(model_id: str, current_user: dict = Depends(get_current_user)):
    """删除指定模型文件（含观测规格旁车 meta），服务端校验 ID 合法性防路径穿越。"""
    # 延迟导入：同上，删除本身轻量但 RLService 构造依赖训练栈
    from services.rl_service import RLService

    try:
        RLService().delete_saved_model(model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(code=0, message="模型已删除", data={"model_id": model_id})


@router.post("/walk-forward")
@handle_rl_exceptions
async def run_walk_forward(req: WalkForwardRequest, current_user: dict = Depends(get_current_user)):
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
