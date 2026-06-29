# -*- coding: utf-8 -*-
"""
回测引擎服务模块（基于 axond 体系）

封装事件驱动回测引擎的初始化、数据加载、策略加载和执行流程。
将原本分散在 cli.py 和 service.py 中的引擎操作逻辑统一到此模块。
完全基于 axond.BacktestEngine，不依赖任何外部量化框架。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class EventDrivenBacktestService:
    """
    事件驱动回测引擎服务（基于 axond 体系）

    封装事件驱动引擎的完整生命周期管理：
    1. 数据加载（通过 BacktestDataProvider）
    2. 引擎初始化（AxonBacktestEngine）
    3. 数据转换并加载到引擎
    4. 策略加载和实例化
    5. 回测执行
    6. 结果格式化

    使用示例：
        from backtest.data_provider import BacktestDataProvider
        from backtest.engine_service import EventDrivenBacktestService

        provider = BacktestDataProvider()
        service = EventDrivenBacktestService(provider)

        results = service.run_backtest(
            strategy_name="simple_dual_ma",
            strategy_params={"fast_period": 10},
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            engine_config={"initial_capital": 100000}
        )
    """

    def __init__(self, data_provider):
        """
        初始化引擎服务

        Args:
            data_provider: BacktestDataProvider 实例
        """
        self.provider = data_provider

    def run_backtest(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        symbols: List[str],
        timeframes: List[str],
        engine_config: Optional[Dict] = None,
        show_progress: bool = False,
    ) -> Dict:
        """
        执行完整的事件驱动回测流程

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            symbols: 品种列表
            timeframes: 时间周期列表
            engine_config: 引擎配置（可选）
            show_progress: 是否显示进度

        Returns:
            dict: 格式化的回测结果
        """
        logger.info(f"[EventDrivenBacktestService] 开始执行回测: {strategy_name}")

        # 解析默认配置
        init_cash = (engine_config or {}).get("initial_capital", 10000)

        # 1. 加载数据
        if show_progress:
            print("\n[1/5] 正在加载数据...")

        data_dict, _ = self.provider.load_multiple(
            symbols=symbols,
            timeframes=timeframes,
            candle_type="spot",
            time_range=(engine_config or {}).get("time_range"),
            auto_download=False,
            show_progress=show_progress,
        )

        if not data_dict:
            raise ValueError("没有成功加载任何数据，回测无法继续")

        # 2. 初始化引擎
        if show_progress:
            print("[2/5] 正在初始化引擎...")

        engine = self._initialize_engine(
            engine_config=engine_config,
            strategy_name=strategy_name,
            init_cash=init_cash,
        )

        # 3. 加载数据到引擎
        if show_progress:
            print("[3/5] 正在加载数据到引擎...")

        for key, df in data_dict.items():
            # key 格式: "BTCUSDT_1h"
            parts = key.rsplit("_", 1)
            symbol = parts[0] if len(parts) > 1 else key
            engine.add_data(df, symbol)

        # 4. 加载策略
        if show_progress:
            print(f"[4/5] 正在加载策略: {strategy_name}...")

        from backtest.strategy_loader_service import StrategyLoaderService

        strategy = StrategyLoaderService.load_strategy(
            name=strategy_name,
            params=strategy_params,
        )

        if strategy is None:
            raise ValueError(f"无法加载策略: {strategy_name}")

        # 注入引擎引用（供策略 buy/sell 时调用）
        strategy._engine = engine

        # 5. 执行回测
        if show_progress:
            print("[5/5] 正在执行回测...")

        # 触发策略启动
        strategy.on_start()
        # 执行回测
        raw_results = engine.run()
        # 触发策略停止
        strategy.on_stop()

        # 6. 格式化结果
        if len(symbols) == 1:
            from backtest.result_formatter_service import ResultFormatterService

            formatted_results = ResultFormatterService.format_event_results(
                results=raw_results,
                symbol=symbols[0],
                timeframe=timeframes[0] if timeframes else "1h",
                strategy_name=strategy_name,
            )
        else:
            # 多品种结果汇总
            formatted_results = self._aggregate_multi_results(
                raw_results=raw_results,
                symbols=symbols,
                timeframe=timeframes[0] if timeframes else "1h",
                strategy_name=strategy_name,
            )

        # 清理资源
        engine.cleanup()

        logger.info(f"[EventDrivenBacktestService] 回测完成")

        return formatted_results

    def _initialize_engine(
        self,
        engine_config: Optional[Dict],
        strategy_name: str,
        init_cash: float,
    ):
        """
        初始化事件驱动引擎

        Args:
            engine_config: 引擎配置字典
            strategy_name: 策略名称
            init_cash: 初始资金

        Returns:
            AxonBacktestEngine: 已初始化的引擎实例
        """
        from backtest.engines.axon_engine import AxonBacktestEngine

        config = {
            "initial_capital": init_cash,
            "log_level": (engine_config or {}).get("log_level", "INFO"),
        }

        engine = AxonBacktestEngine(config)
        engine.initialize()

        logger.info(f"[EventDrivenBacktestService] 引擎初始化完成")
        return engine

    def _aggregate_multi_results(
        self,
        raw_results: dict,
        symbols: List[str],
        timeframe: str,
        strategy_name: str,
    ) -> dict:
        """汇总多品种回测结果"""
        return {
            "strategy_name": strategy_name,
            "symbols": symbols,
            "timeframe": timeframe,
            "is_multi_symbol": True,
            "results_by_symbol": {
                symbol: {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy_name": strategy_name,
                    "metrics": raw_results,
                }
                for symbol in symbols
            },
            "metrics": raw_results,
        }


class DefaultBacktestService:
    """
    默认引擎回测服务（使用 backtesting.py 库）

    用于非事件驱动的传统回测场景。
    """

    def __init__(self, data_provider):
        """
        初始化默认引擎服务

        Args:
            data_provider: BacktestDataProvider 实例
        """
        self.provider = data_provider

    def run_backtest(
        self,
        strategy,
        data_dict: Dict[str, pd.DataFrame],
        config: Dict,
        show_progress: bool = True,
    ) -> Dict:
        """
        执行默认引擎回测

        Args:
            strategy: 策略实例
            data_dict: 数据字典
            config: 回测配置
            show_progress: 是否显示进度

        Returns:
            dict: 回测结果
        """
        from backtesting import Backtest

        if show_progress:
            print("正在执行默认引擎回测...")

        # 从 data_dict 获取第一个品种的数据
        first_key = list(data_dict.keys())[0]
        candles = data_dict[first_key]

        initial_cash = config.get("initial_cash", 10000)
        commission = config.get("commission", 0.001)

        bt = Backtest(
            candles,
            strategy,
            cash=initial_cash,
            commission=commission,
            exclusive_orders=True,
        )

        stats = bt.run()

        return stats
