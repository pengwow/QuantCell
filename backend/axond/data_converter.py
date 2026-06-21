# -*- coding: utf-8 -*-
"""DataFrame ↔ axon 事件格式转换器"""
from __future__ import annotations

from typing import Any

import pandas as pd


def dataframe_to_events(df: pd.DataFrame, symbol: str) -> list[dict[str, Any]]:
    """将 OHLCV DataFrame 转换为 axon BacktestEngine 事件列表。

    Args:
        df: OHLCV DataFrame，索引为 DatetimeIndex。
        symbol: 交易对符号，如 "BTCUSDT"。

    Returns:
        事件字典列表，每个包含 type/timestamp_ns/symbol/open/high/low/close/volume。
    """
    if df.empty:
        return []

    col_map = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in ("open", "high", "low", "close", "volume"):
            col_map[col_lower] = col

    events: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        ts = pd.Timestamp(idx)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        ts_ns = int(ts.timestamp() * 1_000_000_000)

        events.append({
            "type": "market_data",
            "timestamp_ns": ts_ns,
            "symbol": symbol,
            "open": float(row[col_map["open"]]),
            "high": float(row[col_map["high"]]),
            "low": float(row[col_map["low"]]),
            "close": float(row[col_map["close"]]),
            "volume": float(row[col_map.get("volume", "close")]) if "volume" in col_map else 0.0,
        })

    return events


def strategy_signals_to_events(
    signals: list[dict[str, Any]],
    symbol: str,
    start_id: int = 1,
) -> list[dict[str, Any]]:
    """将策略信号列表转换为 axon BacktestEngine 订单事件。

    Args:
        signals: 信号列表，每个包含 action/timestamp_ns/price/quantity。
        symbol: 交易对符号。
        start_id: 起始订单 ID。

    Returns:
        订单事件字典列表。
    """
    events: list[dict[str, Any]] = []
    for i, signal in enumerate(signals):
        order_id = start_id + i
        action = signal["action"].lower()
        side = "Buy" if action == "buy" else "Sell"
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "type": "limit",
            "price": float(signal["price"]),
            "quantity": float(signal["quantity"]),
            "tif": "GTC",
        }
        events.append({
            "type": "order_submitted",
            "timestamp_ns": int(signal["timestamp_ns"]),
            "order": order,
        })
    return events


def axon_result_to_dict(result: Any) -> dict[str, Any]:
    """将 axon RunResult 转换为 QuantCell 结果字典。

    Args:
        result: axon BacktestEngine.run() 返回的 RunResult 对象。

    Returns:
        结果字典，包含 final_nav/total_pnl/max_drawdown/orders_accepted/orders_rejected/fills。
    """
    return {
        "final_nav": result.final_nav,
        "total_pnl": result.total_pnl,
        "max_drawdown": result.max_drawdown,
        "orders_accepted": result.orders_accepted,
        "orders_rejected": result.orders_rejected,
        "fills": result.fills,
    }
