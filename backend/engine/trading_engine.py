# -*- coding: utf-8 -*-
"""TradingEngine — 核心交易引擎（向后兼容门面）

内部委托给 StrategyManager，保持原有 API 兼容性。
"""

from __future__ import annotations

import logging
import time
import uuid
import asyncio
from functools import lru_cache
from typing import Any, Optional

import pandas as pd

from .config import EngineConfig
from backtest.backtest_loop import BacktestResult, RuleStrategy

logger = logging.getLogger(__name__)

# WebSocket 事件推送 topic（保留以保持兼容性）
_WS_TOPIC = "strategy"


@lru_cache(maxsize=1)
def get_risk_service() -> Any:
    """获取 RiskService 单例（包装 axon_bridge.risk.DefaultRiskEngine）。"""
    from services.risk_service import RiskService
    return RiskService()


def _ws_emit(event_type: str, data: dict[str, Any]) -> None:
    """线程安全地将事件推送到 WebSocket 消息队列。"""
    try:
        from websocket.manager import manager
        if manager.message_queue is None:
            return
        message = {
            "type": event_type,
            "topic": _WS_TOPIC,
            "timestamp": int(time.time() * 1000),
            "data": data,
        }
        manager.message_queue.put_nowait(message)
    except Exception:
        # WebSocket 不可用时不阻塞交易逻辑
        pass


_trading_engine_instance: Optional[TradingEngine] = None


def get_trading_engine(config: EngineConfig | None = None) -> TradingEngine:
    """获取 TradingEngine 单例（向后兼容，内部委托给 StrategyManager）。"""
    global _trading_engine_instance
    if _trading_engine_instance is None:
        _trading_engine_instance = TradingEngine(config=config)
    return _trading_engine_instance


class TradingEngine:
    """核心交易引擎（向后兼容门面）

    所有方法内部委托给 StrategyManager，保持原有 API 签名不变。
    """

    def __init__(self, config: EngineConfig | None = None):
        if config is None:
            config = EngineConfig(exchange="binance", trading_mode="paper")
        self._config = config

        # 使用已有的 worker_system 单例，避免重复初始化
        from worker.strategy_manager import worker_system
        self._manager = worker_system

        # 维护自己的策略状态（保持向后兼容）
        self._strategies: dict[str, Any] = {}

        logger.info(
            f"TradingEngine 已初始化（委托模式）: "
            f"exchange={config.exchange}, "
            f"mode={config.trading_mode}"
        )

    @property
    def exchange(self) -> Optional[Any]:
        """返回 exchange adapter"""
        # 延迟导入以避免循环依赖
        try:
            from axon_bridge.exchange import BinanceAdapter, ExchangeConfig
            exchange_config = ExchangeConfig(
                exchange_id=self._config.exchange,
                testnet=self._config.trading_mode == "paper",
            )
            return BinanceAdapter(exchange_config)
        except Exception:
            return None

    @property
    def risk_engine(self) -> Optional[Any]:
        """返回 risk engine"""
        try:
            return get_risk_service()
        except Exception:
            return None

    def engine_status(self) -> dict[str, Any]:
        """返回引擎概览状态"""
        running = sum(1 for rt in self._strategies.values() if rt.get("status") == "running")
        return {
            "exchange": self._config.exchange,
            "mode": self._config.trading_mode,
            "exchange_connected": self.exchange is not None,
            "risk_available": self.risk_engine is not None,
            "total_strategies": len(self._strategies),
            "running_strategies": running,
        }

    def register_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        mode: str = "paper",
    ) -> str:
        """注册策略（内存级别，无持久化）"""
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = {
            "strategy": strategy,
            "symbols": list(symbols),
            "strategy_name": strategy_name or strategy.__class__.__name__,
            "params": params or {},
            "mode": mode,
            "status": "stopped",
            "order_count": 0,
            "fill_count": 0,
            "rejected_count": 0,
            "last_price": 0.0,
            "last_action": None,
            "loop": None,
            "started_at": 0.0,
        }
        logger.info(f"策略已注册: {sid} {symbols}")
        _ws_emit("strategy.registered", {
            "strategy_id": sid,
            "symbols": symbols,
            "strategy_name": strategy_name,
            "mode": mode,
        })
        return sid

    def start_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        account_equity: float = 100_000.0,
        mode: str = "paper",
    ) -> str:
        """启动策略"""
        if self.exchange is None:
            raise RuntimeError(
                "exchange adapter 不可用，无法启动实盘策略。"
                "请确保 axon_quant.exchange 已安装并配置正确。"
            )

        sid = self.register_strategy(
            strategy, symbols, strategy_name, params, mode=mode
        )
        runtime = self._strategies[sid]

        # 创建事件回调，更新 runtime 计数
        def event_callback(event_type: str, data: dict[str, Any]) -> None:
            if event_type == "order.placed":
                runtime["order_count"] += 1
                runtime["last_price"] = data.get("price", runtime["last_price"])
                runtime["last_action"] = data.get("side", "").lower()
            elif event_type == "order.rejected":
                runtime["rejected_count"] += 1
            elif event_type == "bar.processed":
                runtime["last_price"] = data.get("price", runtime["last_price"])
                runtime["last_action"] = data.get("action", runtime["last_action"])
            # 附加 strategy_id 后广播
            data["strategy_id"] = sid
            _ws_emit(event_type, data)

        from strategy.loop import StrategyLoop
        loop = StrategyLoop(
            adapter=self.exchange,
            strategy=strategy,
            symbol=symbols[0],
            risk_engine=self.risk_engine,
            account_equity=account_equity,
            event_callback=event_callback,
        )
        loop.start()

        runtime["loop"] = loop
        runtime["status"] = "running"
        runtime["started_at"] = time.monotonic()

        logger.info(f"策略已启动: {sid} {symbols}")
        _ws_emit("strategy.started", {
            "strategy_id": sid,
            "symbols": symbols,
            "strategy_name": runtime["strategy_name"],
            "mode": mode,
        })
        return sid

    def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略"""
        if strategy_id not in self._strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False

        runtime = self._strategies[strategy_id]
        if runtime.get("loop") is not None:
            runtime["loop"].stop()
        runtime["status"] = "stopped"
        logger.info(f"策略已停止: {strategy_id}")
        _ws_emit("strategy.stopped", {
            "strategy_id": strategy_id,
            "strategy_name": runtime["strategy_name"],
        })
        return True

    def get_strategy_status(self, strategy_id: str) -> Optional[dict[str, Any]]:
        """获取策略状态"""
        runtime = self._strategies.get(strategy_id)
        if runtime is None:
            return None
        # 从 loop 同步最新统计
        loop = runtime.get("loop")
        if loop is not None and hasattr(loop, "stats"):
            stats = loop.stats
            runtime["order_count"] = stats["order_count"]
            runtime["fill_count"] = stats["fill_count"]
            runtime["rejected_count"] = stats["rejected_count"]
            runtime["last_price"] = stats["last_price"]
            runtime["last_action"] = stats["last_action"]
        # 计算运行时间
        duration = time.monotonic() - runtime["started_at"] if runtime["started_at"] > 0 else 0
        return {
            "strategy_id": strategy_id,
            "strategy_name": runtime["strategy_name"],
            "symbols": runtime["symbols"],
            "status": runtime["status"],
            "mode": runtime["mode"],
            "started_at": runtime["started_at"],
            "duration_secs": round(duration, 1),
            "order_count": runtime["order_count"],
            "fill_count": runtime["fill_count"],
            "rejected_count": runtime["rejected_count"],
            "last_action": runtime["last_action"],
            "last_price": runtime["last_price"],
            "realized_pnl": 0.0,
        }

    def list_strategies(self) -> list[dict]:
        """列出所有策略"""
        return [
            self.get_strategy_status(sid) or {"strategy_id": sid, "status": "unknown"}
            for sid in self._strategies
        ]

    def run_backtest(
        self,
        strategy: RuleStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
    ) -> BacktestResult:
        """运行回测（委托给 StrategyManager）"""
        return self._manager.run_backtest(strategy, data, symbol, initial_cash)
