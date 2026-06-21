# -*- coding: utf-8 -*-
"""多品种回测编排器

为每个品种创建独立的 AxonBacktestEngine，汇总结果。
当 axon_quant 的 BacktestEngine 仅支持单品种时，通过外层编排实现多品种回测。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from backtest.engines.axon_engine import AxonBacktestEngine


class MultiSymbolBacktestRunner:
    """多品种回测编排器。

    为每个品种创建独立的 AxonBacktestEngine，汇总结果。

    Args:
        config: 配置字典，支持:
            - initial_capital: 每个品种的初始资金（默认 100000.0）
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._engines: Dict[str, AxonBacktestEngine] = {}
        self._results: Dict[str, dict] = {}

    def add_symbol(self, symbol: str, df: pd.DataFrame) -> None:
        """为指定品种创建引擎并加载数据。

        Args:
            symbol: 交易对符号。
            df: OHLCV DataFrame。
        """
        engine = AxonBacktestEngine(self._config)
        engine.initialize()
        engine.add_data(df, symbol)
        self._engines[symbol] = engine

    def run(self) -> Dict[str, dict]:
        """执行所有品种的回测。

        Returns:
            每个品种的结果字典。
        """
        self._results = {}
        for symbol, engine in self._engines.items():
            try:
                self._results[symbol] = engine.run()
            except Exception as e:
                self._results[symbol] = {"error": str(e)}
        return self._results

    def get_results(self) -> Dict[str, dict]:
        """获取每个品种的独立结果。"""
        return self._results

    def get_portfolio_result(self) -> dict:
        """获取组合级别的汇总结果。"""
        if not self._results:
            return {"error": "尚未执行回测"}

        total_pnl = 0.0
        max_drawdown = 0.0
        total_nav = 0.0
        total_orders_accepted = 0
        total_orders_rejected = 0
        total_fills = 0

        for symbol, result in self._results.items():
            if "error" in result:
                continue
            total_pnl += result.get("total_pnl", 0.0)
            max_drawdown = max(max_drawdown, result.get("max_drawdown", 0.0))
            total_nav += result.get("final_nav", 0.0)
            total_orders_accepted += result.get("orders_accepted", 0)
            total_orders_rejected += result.get("orders_rejected", 0)
            total_fills += result.get("fills", 0)

        return {
            "total_pnl": total_pnl,
            "max_drawdown": max_drawdown,
            "final_nav": total_nav,
            "orders_accepted": total_orders_accepted,
            "orders_rejected": total_orders_rejected,
            "fills": total_fills,
            "symbols_count": len(self._results),
        }

    def cleanup(self) -> None:
        """释放所有引擎资源。"""
        for engine in self._engines.values():
            engine.cleanup()
        self._engines.clear()
        self._results.clear()
