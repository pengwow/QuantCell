# -*- coding: utf-8 -*-
"""RL 模块 API 路由

路由前缀: /api/rl
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from utils.logger import get_logger, LogType
from common.schemas import ApiResponse

from .service import RLService

logger = get_logger(__name__, LogType.APPLICATION)

_rl_service: Optional[RLService] = None


def get_rl_service() -> RLService:
    global _rl_service
    if _rl_service is None:
        _rl_service = RLService()
    return _rl_service


router = APIRouter(prefix="/api/rl", tags=["rl"])


class RLTrainRequest(BaseModel):
    symbol: str = Field(..., description="交易对")
    algorithm: str = Field(default="ppo", description="算法")
    timesteps: int = Field(default=10_000, description="训练步数")
    learning_rate: float = Field(default=3e-4, description="学习率")
    reward: str = Field(default="pnl", description="奖励函数")
    initial_capital: float = Field(default=100_000, description="初始资金")
    transaction_cost: float = Field(default=0.001, description="交易费率")
    interval: str = Field(default="1h", description="K线周期")
    lookback_days: int = Field(default=90, description="回看天数")
    output_name: Optional[str] = Field(default=None, description="模型名称")


@router.post("/train", response_model=ApiResponse)
def train_model(req: RLTrainRequest) -> ApiResponse:
    """启动 RL 训练"""
    try:
        from .models import RLTrainConfig
        config = RLTrainConfig(**req.model_dump())
        result = get_rl_service().train(config)
        return ApiResponse(code=0, message="训练完成", data=result)
    except Exception as e:
        logger.error(f"RL 训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models", response_model=ApiResponse)
def list_models() -> ApiResponse:
    """列出已训练模型"""
    try:
        models = get_rl_service().list_models()
        return ApiResponse(code=0, message="success", data={"models": models})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RLBacktestRequest(BaseModel):
    model_path: str = Field(..., description="模型路径")
    symbol: str = Field(default="BTCUSDT", description="交易对")
    interval: str = Field(default="1h", description="K线周期")
    lookback_days: int = Field(default=90, description="回看天数")


@router.post("/backtest", response_model=ApiResponse)
def backtest_model(req: RLBacktestRequest) -> ApiResponse:
    """用训练好的模型回测"""
    try:
        result = get_rl_service().backtest(
            model_path=req.model_path,
            symbol=req.symbol,
            interval=req.interval,
            lookback_days=req.lookback_days,
        )
        return ApiResponse(code=0, message="回测完成", data=result)
    except Exception as e:
        logger.error(f"RL 回测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
