# -*- coding: utf-8 -*-
"""StrategyLoop — 实盘策略循环

使用 axon_quant.exchange adapter 获取行情，
执行策略生成的 Action 订单。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from axon_quant import Action, limit_order

logger = logging.getLogger(__name__)


class StrategyLoop:
    """实盘策略循环

    Args:
        adapter: 交易所适配器（axon_quant.exchange.*Adapter）
        strategy: 策略实例（实现 on_bar → Action）
        symbol: 交易对符号
        interval: 轮询间隔（秒）
    """

    def __init__(
        self,
        adapter: Any,
        strategy: Any,
        symbol: str,
        interval: float = 1.0,
    ):
        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._order_counter = 0

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._adapter.connect()
        if hasattr(self._adapter, "subscribe"):
            self._adapter.subscribe([self._symbol])

        self._strategy.on_start()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"StrategyLoop 已启动: {self._symbol}")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._strategy.on_stop()
        self._adapter.disconnect()
        logger.info(f"StrategyLoop 已停止: {self._symbol}")

    def _run_loop(self) -> None:
        while self._running:
            try:
                ticker = self._adapter.get_ticker(self._symbol)
                bar = {
                    "open": float(ticker.get("open", 0.0)),
                    "high": float(ticker.get("high", 0.0)),
                    "low": float(ticker.get("low", 0.0)),
                    "close": float(ticker.get("last", 0.0)),
                    "volume": float(ticker.get("volume", 0.0)),
                    "symbol": self._symbol,
                    "timestamp_ns": int(time.time() * 1_000_000_000),
                }

                action = self._strategy.on_bar(bar)
                if str(action.action_type) in ("buy", "sell"):
                    self._execute_action(action, bar["close"])

            except Exception as e:
                logger.error(f"StrategyLoop 错误: {e}", exc_info=True)

            time.sleep(self._interval)

    def _execute_action(self, action: Action, current_price: float) -> None:
        try:
            side = "Buy" if str(action.action_type) == "buy" else "Sell"
            quantity = abs(action.target_position) if action.target_position else 0.1
            price = current_price

            order_dict = {
                "symbol": self._symbol,
                "side": side,
                "type": "limit",
                "quantity": quantity,
                "price": price,
                "tif": "GTC",
            }

            result = self._adapter.place_order(order_dict)
            logger.info(f"订单已执行: {order_dict} -> {result}")

        except Exception as e:
            logger.error(f"订单执行失败: {e}")
