# -*- coding: utf-8 -*-
"""TradingEngine — 核心交易引擎

统一管理策略生命周期，注入 exchange adapter + risk engine，
桥接 backtest ↔ live。

设计文档: docs/compose/specs/2026-06-24-core-trading-engine-design.md
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import pandas as pd

from .config import EngineConfig
from .strategy_runtime import StrategyRuntime
from backtest.backtest_loop import BacktestLoop, BacktestResult
from strategy.core.unified_strategy import UnifiedStrategy

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant.exchange import (
        BinanceAdapter as _BinanceAdapter,
        OkxAdapter as _OkxAdapter,
        ExchangeConfig as _ExchangeConfig,
    )
    EXCHANGE_AVAILABLE = True
except ImportError:
    EXCHANGE_AVAILABLE = False
    _BinanceAdapter = None
    _OkxAdapter = None
    _ExchangeConfig = None

try:
    from axon_quant.risk import (
        DefaultRiskEngine as _DefaultRiskEngine,
        RiskConfig as _RiskConfig,
    )
    RISK_AVAILABLE = True
except ImportError:
    RISK_AVAILABLE = False
    _DefaultRiskEngine = None
    _RiskConfig = None


class TradingEngine:
    """核心交易引擎

    统一管理策略生命周期，注入 exchange adapter + risk engine。

    Args:
        config: 引擎配置

    Example:
        >>> config = EngineConfig(exchange="binance", trading_mode="paper")
        >>> engine = TradingEngine(config)
        >>> strategy = DualMAStrategy()
        >>> sid = engine.start_strategy(strategy, ["BTCUSDT"])
        >>> engine.stop_strategy(sid)
    """

    def __init__(self, config: EngineConfig):
        """初始化交易引擎

        Args:
            config: 引擎配置
        """
        self._config = config
        self._strategies: dict[str, StrategyRuntime] = {}

        # 初始化 exchange adapter
        self._exchange = self._create_exchange_adapter(config)

        # 初始化 risk engine
        self._risk_engine = self._create_risk_engine(config)

        logger.info(
            f"TradingEngine 已初始化: "
            f"exchange={config.exchange}, "
            f"mode={config.trading_mode}, "
            f"exchange_available={self._exchange is not None}, "
            f"risk_available={self._risk_engine is not None}"
        )

    def _create_exchange_adapter(self, config: EngineConfig) -> Optional[Any]:
        """创建交易所适配器

        Args:
            config: 引擎配置

        Returns:
            交易所适配器实例，如果不可用返回 None
        """
        if not EXCHANGE_AVAILABLE:
            logger.warning("axon_quant.exchange 不可用，跳过 exchange adapter 初始化")
            return None

        try:
            if config.exchange == "binance":
                # 创建 Binance 适配器配置
                exchange_config = _ExchangeConfig(
                    exchange_id="binance",
                    testnet=config.trading_mode == "paper",
                )
                return _BinanceAdapter(exchange_config)
            elif config.exchange == "okx":
                # 创建 OKX 适配器配置
                exchange_config = _ExchangeConfig(
                    exchange_id="okx",
                    testnet=config.trading_mode == "paper",
                )
                return _OkxAdapter(exchange_config)
            else:
                logger.warning(f"不支持的交易所: {config.exchange}")
                return None
        except Exception as e:
            logger.error(f"创建 exchange adapter 失败: {e}")
            return None

    def _create_risk_engine(self, config: EngineConfig) -> Optional[Any]:
        """创建风控引擎

        Args:
            config: 引擎配置

        Returns:
            风控引擎实例，如果不可用返回 None
        """
        if not RISK_AVAILABLE:
            logger.warning("axon_quant.risk 不可用，跳过 risk engine 初始化")
            return None

        try:
            risk_config = _RiskConfig(**config.risk_config)
            return _DefaultRiskEngine(risk_config)
        except Exception as e:
            logger.error(f"创建 risk engine 失败: {e}")
            return None

    @property
    def exchange(self) -> Optional[Any]:
        """获取 exchange adapter"""
        return self._exchange

    @property
    def risk_engine(self) -> Optional[Any]:
        """获取 risk engine"""
        return self._risk_engine

    def register_strategy(self, strategy: UnifiedStrategy, symbols: list[str]) -> str:
        """注册策略（不启动）

        Args:
            strategy: 策略实例
            symbols: 交易对列表

        Returns:
            strategy_id: 策略 ID
        """
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid, strategy=strategy, symbols=symbols
        )
        logger.info(f"策略已注册: {sid} {symbols}")
        return sid

    def start_strategy(self, strategy: UnifiedStrategy, symbols: list[str]) -> str:
        """启动实盘策略

        Args:
            strategy: 策略实例
            symbols: 交易对列表

        Returns:
            strategy_id: 策略 ID

        Raises:
            RuntimeError: 如果 exchange adapter 不可用
        """
        if self._exchange is None:
            raise RuntimeError(
                "exchange adapter 不可用，无法启动实盘策略。"
                "请确保 axon_quant.exchange 已安装并配置正确。"
            )

        sid = str(uuid.uuid4())[:8]

        # 创建 StrategyLoop
        from axond.strategy_loop import StrategyLoop
        loop = StrategyLoop(
            adapter=self._exchange,
            strategy=strategy,
            symbol=symbols[0],
        )

        # 启动循环
        loop.start()

        # 注册到策略列表
        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid,
            strategy=strategy,
            symbols=symbols,
            loop=loop,
            status="running"
        )

        logger.info(f"策略已启动: {sid} {symbols}")
        return sid

    def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略

        Args:
            strategy_id: 策略 ID

        Returns:
            是否停止成功
        """
        if strategy_id not in self._strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False

        runtime = self._strategies[strategy_id]

        # 停止循环
        if hasattr(runtime, 'loop') and runtime.loop is not None:
            runtime.loop.stop()

        runtime.status = "stopped"
        logger.info(f"策略已停止: {strategy_id}")
        return True

    def list_strategies(self) -> list[dict]:
        """获取策略列表

        Returns:
            策略信息列表
        """
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
        strategy: UnifiedStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
    ) -> BacktestResult:
        """执行回测

        Args:
            strategy: 策略实例
            data: OHLCV DataFrame
            symbol: 交易对符号
            initial_cash: 初始资金

        Returns:
            BacktestResult 回测结果
        """
        loop = BacktestLoop(initial_cash=initial_cash)
        return loop.run(strategy, data, symbol)
