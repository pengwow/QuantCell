# -*- coding: utf-8 -*-
"""StrategyLoop — 实盘策略循环

使用 axon_quant.exchange adapter 获取行情，
执行策略生成的订单。

设计文档: docs/compose/specs/2026-06-24-core-trading-engine-design.md
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide
from strategy.core.unified_strategy import StrategyContext, UnifiedStrategy

logger = logging.getLogger(__name__)


class StrategyLoop:
    """实盘策略循环

    使用 axon_quant.exchange adapter 获取行情，
    执行策略生成的订单。

    Args:
        adapter: 交易所适配器（axon_quant.exchange.*Adapter 或 ExchangeAdapter）
        strategy: 策略实例
        symbol: 交易对符号
        interval: 轮询间隔（秒）

    Example:
        >>> from exchange.axon_exchange_adapter import ExchangeAdapter
        >>> adapter = ExchangeAdapter("binance", testnet=True)
        >>> strategy = DualMAStrategy()
        >>> loop = StrategyLoop(adapter, strategy, "BTCUSDT")
        >>> loop.start()
        >>> # ... 运行一段时间 ...
        >>> loop.stop()
    """

    def __init__(
        self,
        adapter: Any,
        strategy: UnifiedStrategy,
        symbol: str,
        interval: float = 1.0,
    ):
        """初始化策略循环

        Args:
            adapter: 交易所适配器
            strategy: 策略实例
            symbol: 交易对符号
            interval: 轮询间隔（秒）
        """
        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ctx = StrategyContext()

    @property
    def symbol(self) -> str:
        """获取交易对符号"""
        return self._symbol

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running

    def start(self) -> None:
        """启动策略循环"""
        # 连接交易所
        self._adapter.connect()

        # 订阅行情
        if hasattr(self._adapter, 'subscribe'):
            self._adapter.subscribe([self._symbol])

        # 策略启动回调
        self._strategy.on_start(self._ctx)

        # 启动循环线程
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info(f"StrategyLoop 已启动: {self._symbol}")

    def stop(self) -> None:
        """停止策略循环"""
        # 停止循环
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

        # 策略停止回调
        self._strategy.on_stop(self._ctx)

        # 断开交易所连接
        self._adapter.disconnect()

        logger.info(f"StrategyLoop 已停止: {self._symbol}")

    def _run_loop(self) -> None:
        """主循环"""
        while self._running:
            try:
                # 获取行情
                ticker = self._adapter.get_ticker(self._symbol)

                # 创建 Bar 对象
                bar = Bar(
                    timestamp=int(time.time() * 1_000_000_000),
                    open=float(ticker.get("open", 0.0)),
                    high=float(ticker.get("high", 0.0)),
                    low=float(ticker.get("low", 0.0)),
                    close=float(ticker.get("last", 0.0)),
                    volume=float(ticker.get("volume", 0.0)),
                    symbol=self._symbol,
                )

                # 策略处理 Bar，生成订单
                orders = self._strategy.on_bar(bar, self._ctx)

                # 执行订单
                for order in orders:
                    self._execute_order(order)

            except Exception as e:
                logger.error(f"StrategyLoop 错误: {e}", exc_info=True)

            # 等待下一次轮询
            time.sleep(self._interval)

    def _execute_order(self, order: Order) -> None:
        """执行订单

        Args:
            order: 订单对象
        """
        try:
            # 构建订单字典
            order_dict = {
                "symbol": order.symbol or self._symbol,
                "side": "Buy" if order.side == OrderSide.BUY else "Sell",
                "type": "limit" if order.price > 0 else "market",
                "quantity": order.quantity,
                "tif": "GTC",
            }

            # 限价单添加价格
            if order.price > 0:
                order_dict["price"] = order.price

            # 下单
            result = self._adapter.place_order(order_dict)
            logger.info(f"订单已执行: {order_dict} -> {result}")

        except Exception as e:
            logger.error(f"订单执行失败: {e}", exc_info=True)
