# -*- coding: utf-8 -*-
"""TradingEngine — 核心交易引擎

统一管理策略生命周期，注入 exchange adapter + risk engine，
桥接 backtest ↔ live。单例模式，通过 get_trading_engine() 获取。
"""

from __future__ import annotations

import logging
import time
import uuid
from functools import lru_cache
from typing import Any, Optional

import pandas as pd

from .config import EngineConfig
from .strategy_runtime import StrategyRuntime
from backtest.backtest_loop import BacktestLoop, BacktestResult, RuleStrategy
from strategy.loop import StrategyLoop

from axon_bridge.exchange import (
    BinanceAdapter,
    OkxAdapter,
    ExchangeConfig,
)

logger = logging.getLogger(__name__)

# WebSocket 事件推送 topic
_WS_TOPIC = "strategy"


@lru_cache(maxsize=1)
def get_risk_service() -> Any:
    """获取 RiskService 单例（包装 axon_bridge.risk.DefaultRiskEngine）。"""
    from services.risk_service import RiskService
    return RiskService()


def _ws_emit(event_type: str, data: dict[str, Any]) -> None:
    """线程安全地将事件推送到 WebSocket 消息队列。

    StrategyLoop 运行在独立线程中，通过 manager.message_queue.put_nowait
    跨线程投递消息，与 core/lifespan.py 中 kline_consumer 的模式一致。
    """
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


class TradingEngine:
    """核心交易引擎"""

    def __init__(self, config: EngineConfig):
        self._config = config
        self._strategies: dict[str, StrategyRuntime] = {}
        self._exchange = self._create_exchange_adapter(config)
        self._risk_engine = self._create_risk_engine(config)

        logger.info(
            f"TradingEngine 已初始化: "
            f"exchange={config.exchange}, "
            f"mode={config.trading_mode}"
        )

    def _create_exchange_adapter(self, config: EngineConfig) -> Optional[Any]:
        try:
            if config.exchange == "binance":
                exchange_config = ExchangeConfig(
                    exchange_id="binance",
                    testnet=config.trading_mode == "paper",
                )
                return BinanceAdapter(exchange_config)
            elif config.exchange == "okx":
                exchange_config = ExchangeConfig(
                    exchange_id="okx",
                    testnet=config.trading_mode == "paper",
                )
                return OkxAdapter(exchange_config)
            else:
                logger.warning(f"不支持的交易所: {config.exchange}")
                return None
        except Exception as e:
            logger.error(f"创建 exchange adapter 失败: {e}")
            return None

    def _create_risk_engine(self, config: EngineConfig) -> Optional[Any]:
        """创建 RiskService 单例作为实盘风控检查器。"""
        try:
            return get_risk_service()
        except Exception as e:
            logger.error(f"创建 risk engine 失败: {e}")
            return None

    @property
    def exchange(self) -> Optional[Any]:
        return self._exchange

    @property
    def risk_engine(self) -> Optional[Any]:
        return self._risk_engine

    def engine_status(self) -> dict[str, Any]:
        """返回引擎概览状态"""
        running = sum(1 for rt in self._strategies.values() if rt.status == "running")
        return {
            "exchange": self._config.exchange,
            "mode": self._config.trading_mode,
            "exchange_connected": self._exchange is not None,
            "risk_available": self._risk_engine is not None,
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
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid,
            strategy=strategy,
            symbols=list(symbols),
            strategy_name=strategy_name or strategy.__class__.__name__,
            params=params or {},
            mode=mode,
        )
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
        if self._exchange is None:
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
                runtime.order_count += 1
                runtime.last_price = data.get("price", runtime.last_price)
                runtime.last_action = data.get("side", "").lower()
            elif event_type == "order.rejected":
                runtime.rejected_count += 1
            elif event_type == "bar.processed":
                runtime.last_price = data.get("price", runtime.last_price)
                runtime.last_action = data.get("action", runtime.last_action)
            # 附加 strategy_id 后广播
            data["strategy_id"] = sid
            _ws_emit(event_type, data)

        loop = StrategyLoop(
            adapter=self._exchange,
            strategy=strategy,
            symbol=symbols[0],
            risk_engine=self._risk_engine,
            account_equity=account_equity,
            event_callback=event_callback,
        )
        loop.start()

        runtime.loop = loop
        runtime.status = "running"
        runtime.started_at = time.monotonic()

        logger.info(f"策略已启动: {sid} {symbols}")
        _ws_emit("strategy.started", {
            "strategy_id": sid,
            "symbols": symbols,
            "strategy_name": runtime.strategy_name,
            "mode": mode,
        })
        return sid

    def stop_strategy(self, strategy_id: str) -> bool:
        if strategy_id not in self._strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False

        runtime = self._strategies[strategy_id]
        if runtime.loop is not None:
            runtime.loop.stop()
        runtime.status = "stopped"
        logger.info(f"策略已停止: {strategy_id}")
        _ws_emit("strategy.stopped", {
            "strategy_id": strategy_id,
            "strategy_name": runtime.strategy_name,
        })
        return True

    def get_strategy_status(self, strategy_id: str) -> Optional[dict[str, Any]]:
        runtime = self._strategies.get(strategy_id)
        if runtime is None:
            return None
        # 从 loop 同步最新统计
        if runtime.loop is not None and hasattr(runtime.loop, "stats"):
            stats = runtime.loop.stats
            runtime.order_count = stats["order_count"]
            runtime.fill_count = stats["fill_count"]
            runtime.rejected_count = stats["rejected_count"]
            runtime.last_price = stats["last_price"]
            runtime.last_action = stats["last_action"]
        return runtime.to_dict()

    def list_strategies(self) -> list[dict]:
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
        loop = BacktestLoop(initial_cash=initial_cash)
        return loop.run(strategy, data, symbol)


_trading_engine_instance: Optional[TradingEngine] = None


def get_trading_engine(config: EngineConfig | None = None) -> TradingEngine:
    """获取 TradingEngine 单例。首次调用需传入 config（后续调用忽略）。"""
    global _trading_engine_instance
    if _trading_engine_instance is None:
        if config is None:
            config = EngineConfig(exchange="binance", trading_mode="paper")
        _trading_engine_instance = TradingEngine(config)
    return _trading_engine_instance
