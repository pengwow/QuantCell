"""RL Training API routes."""

import functools
import json
from datetime import UTC, datetime

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


class RLBacktestRequest(BaseModel):
    model_id: str  # data/models 下 .zip 文件 stem（统一模型总表传 file_name 去掉 .zip）
    symbol: str  # 回测目标交易对，如 BTCUSDT
    interval: str = "1h"
    candle_type: str = "spot"
    initial_capital: float = 100_000.0
    # 非空时跑集成员聚合回测（engine 固定 kernel），model_id 仅作兜底不做存在性校验
    ensemble_id: str | None = None


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


@router.post("/backtest")
@handle_rl_exceptions
async def backtest_model(req: RLBacktestRequest, current_user: dict = Depends(get_current_user)):
    """用已训练 RL 模型回测（统一内核口径），结果任务化落盘并返回 task_id。

    结果按策略回测同一契约落盘（文件任务 + 结果 JSON + backtest_tasks 表行），
    回测列表 / 详情 / 回放页零感知复用；前端凭 task_id 跳完整详情页。
    引擎固定 kernel（与实盘同一条主回路）；kernel 回测为秒级，采用同步执行。
    """
    from services.rl_service import RLService

    svc = RLService()
    if not req.ensemble_id:
        # 集成回测的具体成员校验在 service 层（load_ensemble_spec）；单模型在此做
        # 路径安全解析与存在性校验，404 早于执行
        try:
            model_path = svc.resolve_saved_model_path(req.model_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not model_path.is_file():
            raise HTTPException(status_code=404, detail=f"模型不存在: {req.model_id}")

    result = svc.run_backtest_task(
        req.model_id,
        req.symbol,
        interval=req.interval,
        candle_type=req.candle_type,
        initial_capital=req.initial_capital,
        ensemble_id=req.ensemble_id,
    )

    # DB 任务行：详情 / replay / 列表筛选共享 backtest_tasks 表（import 方式与
    # backtest/routes.py 的既有模式一致——函数内 import 避免 API 启动拉起 ORM）
    from backtest.models import BacktestTask
    from utils.db_session import get_db_session

    now = datetime.now(UTC)
    config_json = json.dumps(
        {
            "symbols": [req.symbol],
            "interval": req.interval,
            "initial_capital": req.initial_capital,
            "engine_type": "axon",
            "data_type": "kline",
            "trading_mode": "spot" if req.candle_type == "spot" else "futures",
            "source": "rl_model_backtest",
        },
        default=str,
        ensure_ascii=False,
    )
    with get_db_session() as db:
        task = BacktestTask(
            id=result["task_id"],
            strategy_name=result["strategy_name"],
            backtest_config=config_json,
            status="completed",
            started_at=now,
            completed_at=now,
        )
        db.add(task)
        db.commit()

    return ApiResponse(code=0, message="回测完成", data=result)


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
