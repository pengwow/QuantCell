# -*- coding: utf-8 -*-
"""TradingEngine — 核心交易引擎

统一管理策略生命周期，注入 exchange adapter + risk engine，
桥接 backtest ↔ live。
"""

from __future__ import annotations

import logging
import uuid
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
from axon_bridge.risk import (
    DefaultRiskEngine,
    RiskConfig,
)

logger = logging.getLogger(__name__)


class TradingEngine:
    """核心交易引擎

    统一管理策略生命周期，注入 exchange adapter + risk engine。

    Args:
        config: 引擎配置

    Example:
        >>> config = EngineConfig(exchange="binance", trading_mode="paper")
        >>> engine = TradingEngine(config)
        >>> strategy = DualMA()
        >>> sid = engine.start_strategy(strategy, ["BTCUSDT"])
        >>> engine.stop_strategy(sid)
    """

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
        try:
            risk_config = RiskConfig(**config.risk_config)
            return DefaultRiskEngine(risk_config)
        except Exception as e:
            logger.error(f"创建 risk engine 失败: {e}")
            return None

    @property
    def exchange(self) -> Optional[Any]:
        return self._exchange

    @property
    def risk_engine(self) -> Optional[Any]:
        return self._risk_engine

    def register_strategy(self, strategy: RuleStrategy, symbols: list[str]) -> str:
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid, strategy=strategy, symbols=symbols
        )
        logger.info(f"策略已注册: {sid} {symbols}")
        return sid

    def start_strategy(self, strategy: RuleStrategy, symbols: list[str]) -> str:
        if self._exchange is None:
            raise RuntimeError(
                "exchange adapter 不可用，无法启动实盘策略。"
                "请确保 axon_quant.exchange 已安装并配置正确。"
            )

        sid = str(uuid.uuid4())[:8]

        loop = StrategyLoop(
            adapter=self._exchange,
            strategy=strategy,
            symbol=symbols[0],
        )
        loop.start()

        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid,
            strategy=strategy,
            symbols=symbols,
            loop=loop,
            status="running",
        )

        logger.info(f"策略已启动: {sid} {symbols}")
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
        return True

    def list_strategies(self) -> list[dict]:
        return [
            {
                "id": s.strategy_id,
                "status": s.status,
                "symbols": s.symbols,
            }
            for s in self._strategies.values()
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
