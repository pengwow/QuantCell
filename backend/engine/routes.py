# -*- coding: utf-8 -*-
"""Engine API routes — 交易引擎管理和策略运行控制"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from common.schemas import ApiResponse
from strategy.loader import StrategyLoader
from strategy.base import StrategyConfig
from utils.auth import jwt_auth_required

router = APIRouter(prefix="/api/engine", tags=["Engine"])


def _sanitize(obj: Any) -> Any:
    """替换 NaN/inf 为 None，确保 JSON 可序列化"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


# ---------- 请求模型 ----------

class StartStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="策略模板名（已注册）")
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])
    mode: str = Field(default="paper", description="paper | live")
    params: dict[str, Any] = Field(default_factory=dict)
    initial_cash: float = Field(default=100_000.0, gt=0)
    account: str | None = Field(default=None, description="凭证名（live 模式需要）")


class BacktestRequest(BaseModel):
    strategy_name: str = Field(..., description="策略模板名")
    symbol: str = Field(default="BTCUSDT")
    data: list[dict[str, Any]] = Field(..., min_length=1, description="OHLCV 数据列表，每条必须包含 open/high/low/close/volume")
    params: dict[str, Any] = Field(default_factory=dict)
    initial_cash: float = Field(default=100_000.0, gt=0)
    # ponytail: v1 仅支持请求体传入 data，数据库查询数据源后续接入


# ---------- 端点 ----------

@router.get("/status")
@jwt_auth_required
async def engine_status(request: Request) -> ApiResponse:
    """获取引擎状态概览"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    return ApiResponse(code=0, message="ok", data=engine.engine_status())


@router.get("/strategies")
@jwt_auth_required
async def list_strategies(request: Request) -> ApiResponse:
    """列出所有策略及其运行状态"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    return ApiResponse(code=0, message="ok", data=engine.list_strategies())


@router.post("/strategies/start")
@jwt_auth_required
async def start_strategy(request: Request, req: StartStrategyRequest) -> ApiResponse:
    """启动策略（paper 或 live 模式）"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()

    # 加载策略类
    strategy_cls = StrategyLoader.get(req.strategy_name)
    config = StrategyConfig(
        name=req.strategy_name,
        symbol=req.symbols[0],
        params=req.params,
    )
    strategy = strategy_cls(config)

    if req.mode == "live" and not req.account:
        raise HTTPException(status_code=400, detail="live 模式必须指定 account 凭证名")

    sid = engine.start_strategy(
        strategy=strategy,
        symbols=req.symbols,
        strategy_name=req.strategy_name,
        params=req.params,
        account_equity=req.initial_cash,
        mode=req.mode,
    )
    return ApiResponse(
        code=0,
        message="策略启动成功",
        data={"strategy_id": sid, "status": "running", "mode": req.mode},
    )


@router.post("/strategies/{sid}/stop")
@jwt_auth_required
async def stop_strategy(request: Request, sid: str) -> ApiResponse:
    """停止运行中的策略"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    ok = engine.stop_strategy(sid)
    if not ok:
        raise HTTPException(status_code=404, detail=f"策略 {sid} 不存在")
    return ApiResponse(code=0, message="策略已停止", data={"strategy_id": sid})


@router.get("/strategies/{sid}/status")
@jwt_auth_required
async def get_strategy_status(request: Request, sid: str) -> ApiResponse:
    """获取单个策略运行详情"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    status = engine.get_strategy_status(sid)
    if status is None:
        raise HTTPException(status_code=404, detail=f"策略 {sid} 不存在")
    return ApiResponse(code=0, message="ok", data=status)


@router.post("/backtest")
@jwt_auth_required
async def run_backtest(request: Request, req: BacktestRequest) -> ApiResponse:
    """运行回测"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()

    # 加载策略
    strategy_cls = StrategyLoader.get(req.strategy_name)
    config = StrategyConfig(
        name=req.strategy_name,
        symbol=req.symbol,
        params=req.params,
    )
    strategy = strategy_cls(config)

    # 数据加载：v1 要求请求体直接提供 OHLCV data 列表
    df = pd.DataFrame(req.data)
    # 兼容大小写列名
    col_map = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    for upper, lower in col_map.items():
        if lower not in df.columns and upper in df.columns:
            df[lower] = df[upper]
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"数据缺少必要列: {missing}")

    # 若有 timestamp 列，尝试设为索引以兼容 BacktestLoop 的 DatetimeIndex 处理
    if "timestamp" in df.columns:
        try:
            df.index = pd.to_datetime(df["timestamp"], unit="ns", utc=True)
        except Exception:
            pass

    if len(df) == 0:
        raise HTTPException(status_code=400, detail="数据为空，无法回测")

    result = engine.run_backtest(
        strategy=strategy,
        data=df,
        symbol=req.symbol,
        initial_cash=req.initial_cash,
    )

    return ApiResponse(
        code=0,
        message="回测完成",
        data=_sanitize({
            "total_pnl": result.total_pnl,
            "total_orders": result.total_orders,
            "fills": result.fills,
            "final_nav": result.final_nav,
            "max_drawdown": result.max_drawdown,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "sharpe_ratio": result.sharpe_ratio,
            "total_fees": result.total_fees,
            "nav_peak": result.nav_peak,
            "bar_count": result.bar_count,
            "equity_curve": result.equity_curve,
            "trade_records": result.trade_records,
        }),
    )
