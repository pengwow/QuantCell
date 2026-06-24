# -*- coding: utf-8 -*-
"""基于 axon_quant 的回测引擎

替代原 axon_quant BacktestEngine，使用 axon_quant.backtest.BacktestEngine。
当 axon_quant 不可用时提供清晰的错误信息。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from axond.data_converter import dataframe_to_events, axon_result_to_dict

try:
    from axon_quant.backtest import BacktestEngine as _AxonBacktestEngine
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _AxonBacktestEngine = None


class AxonBacktestEngine:
    """基于 axon_quant 的事件驱动回测引擎。

    使用 axon_quant.backtest.BacktestEngine 作为底层引擎，
    通过 push_event() 推入市场数据和订单事件，run() 执行回测。

    Args:
        config: 配置字典，支持:
            - initial_capital: 初始资金（默认 100000.0）
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._engine: Any = None
        self._events: list[dict] = []
        self._is_initialized = False

    def initialize(self) -> None:
        """初始化回测引擎"""
        if not AXON_AVAILABLE:
            raise ImportError(
                "axon_quant 未安装或无法导入。"
                "请确保 Python >= 3.14 并安装 axon_quant: "
                "cd /path/to/axon && maturin develop --release"
            )
        initial_cash = self._config.get("initial_capital", 100000.0)
        self._engine = _AxonBacktestEngine(initial_cash=initial_cash)
        self._is_initialized = True

    def add_data(self, df: pd.DataFrame, symbol: str) -> None:
        """将 DataFrame 数据转为事件并添加到引擎。

        Args:
            df: OHLCV DataFrame，索引为 DatetimeIndex。
            symbol: 交易对符号。
        """
        self._ensure_initialized()
        events = dataframe_to_events(df, symbol)
        for event in events:
            self._engine.push_event(event)
        self._events.extend(events)

    def submit_order(self, order_dict: dict, timestamp_ns: int) -> None:
        """提交订单事件到引擎。

        Args:
            order_dict: 订单字典（符合 axon 协议）。
            timestamp_ns: 纳秒时间戳。
        """
        self._ensure_initialized()
        self._engine.push_event({
            "type": "order_submitted",
            "timestamp_ns": timestamp_ns,
            "order": order_dict,
        })
        self._events.append({
            "type": "order_submitted",
            "timestamp_ns": timestamp_ns,
            "order": order_dict,
        })

    def run(self) -> dict:
        """执行回测并返回结果。

        Returns:
            结果字典，包含 final_nav/total_pnl/max_drawdown/orders_accepted/orders_rejected/fills。
        """
        self._ensure_initialized()
        result = self._engine.run()
        return axon_result_to_dict(result)

    def cleanup(self) -> None:
        """释放引擎资源"""
        self._engine = None
        self._is_initialized = False

    def _ensure_initialized(self) -> None:
        if not self._is_initialized:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")
