# -*- coding: utf-8 -*-
"""axon 结果格式化器

将 axon BacktestEngine 的 RunResult 转换为 QuantCell 标准结果格式。
"""
from __future__ import annotations

from typing import Any, Dict


def format_backtest_result(
    result: dict,
    symbol: str,
    timeframe: str,
    strategy_name: str,
) -> dict:
    """格式化单品种回测结果。

    Args:
        result: axon RunResult 字典。
        symbol: 交易对符号。
        timeframe: 时间周期。
        strategy_name: 策略名称。

    Returns:
        格式化后的结果字典。
    """
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy_name": strategy_name,
        "metrics": {
            "final_nav": result.get("final_nav", 0.0),
            "total_pnl": result.get("total_pnl", 0.0),
            "max_drawdown": result.get("max_drawdown", 0.0),
            "orders_accepted": result.get("orders_accepted", 0),
            "orders_rejected": result.get("orders_rejected", 0),
            "fills": result.get("fills", 0),
        },
    }


def format_multi_result(
    results: Dict[str, dict],
    timeframe: str,
    strategy_name: str,
) -> dict:
    """格式化多品种回测结果。

    Args:
        results: 每个品种的结果字典。
        timeframe: 时间周期。
        strategy_name: 策略名称。

    Returns:
        格式化后的结果字典，包含每个品种结果和组合汇总。
    """
    per_symbol = {}
    total_pnl = 0.0
    total_nav = 0.0
    max_drawdown = 0.0
    total_accepted = 0
    total_rejected = 0
    total_fills = 0

    for symbol, result in results.items():
        per_symbol[symbol] = format_backtest_result(result, symbol, timeframe, strategy_name)
        total_pnl += result.get("total_pnl", 0.0)
        total_nav += result.get("final_nav", 0.0)
        max_drawdown = max(max_drawdown, result.get("max_drawdown", 0.0))
        total_accepted += result.get("orders_accepted", 0)
        total_rejected += result.get("orders_rejected", 0)
        total_fills += result.get("fills", 0)

    return {
        "per_symbol": per_symbol,
        "portfolio": {
            "total_pnl": total_pnl,
            "final_nav": total_nav,
            "max_drawdown": max_drawdown,
            "orders_accepted": total_accepted,
            "orders_rejected": total_rejected,
            "fills": total_fills,
            "symbols_count": len(results),
        },
        "timeframe": timeframe,
        "strategy_name": strategy_name,
    }
