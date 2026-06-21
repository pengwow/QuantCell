# -*- coding: utf-8 -*-
"""网格挂单验证策略（axon 版本）

使用 AxonStrategy 基类，不依赖 nautilus_trader。
用于验证 Worker 运行情况的功能性测试策略。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict

from axond.axon_strategy import AxonStrategy
from axond.strategy_config import StrategyConfig
from axond.types import Bar, InstrumentId, OrderType


@dataclass
class GridOrderValidationConfig(StrategyConfig):
    """网格挂单验证策略配置"""
    order_size: Decimal = Decimal("0.01")
    grid_levels: int = 3
    grid_spacing_pct: float = 0.3
    refresh_interval_sec: int = 30


class GridOrderValidationStrategy(AxonStrategy):
    """网格挂单验证策略

    在当前价格两侧按固定比例挂网格限价单，用于验证：
    1. Worker 订单执行流程
    2. 日志收集和实时展示
    3. 数据同步到数据库
    4. 订单生命周期管理
    """

    def __init__(self, config: GridOrderValidationConfig):
        if config.grid_levels <= 0:
            raise ValueError(f"grid_levels必须大于0，得到{config.grid_levels}")
        if config.grid_spacing_pct <= 0:
            raise ValueError(f"grid_spacing_pct必须大于0，得到{config.grid_spacing_pct}")
        super().__init__(config)
        self.current_price: float = 0.0
        self.last_refresh_time: float = 0.0
        self.grid_orders: List[dict] = []
        self.order_count: int = 0
        self.success_count: int = 0
        self.fail_count: int = 0

    def on_start(self):
        super().on_start()
        self.current_price = 0.0
        self.last_refresh_time = 0.0
        self.grid_orders = []
        self.order_count = 0
        self.success_count = 0
        self.fail_count = 0

    def on_bar(self, bar: Bar):
        super().on_bar(bar)
        self.current_price = bar.close

        # 检查是否需要刷新网格
        current_time = time.time()
        if current_time - self.last_refresh_time >= self.config.refresh_interval_sec:
            self._refresh_grid(bar)
            self.last_refresh_time = current_time

    def _refresh_grid(self, bar: Bar):
        """刷新网格订单"""
        symbol = bar.instrument_id.symbol

        # 撤销所有现有订单
        for order in self.grid_orders:
            self._cancel_order(order)
        self.grid_orders = []

        # 创建新的网格订单
        spacing = self.config.grid_spacing_pct / 100.0

        for i in range(1, self.config.grid_levels + 1):
            # 买单（低于当前价格）
            buy_price = self.current_price * (1 - spacing * i)
            buy_order = self.buy(
                symbol,
                float(self.config.order_size),
                buy_price,
                OrderType.LIMIT,
            )
            self.grid_orders.append(buy_order)

            # 卖单（高于当前价格）
            sell_price = self.current_price * (1 + spacing * i)
            sell_order = self.sell(
                symbol,
                float(self.config.order_size),
                sell_price,
                OrderType.LIMIT,
            )
            self.grid_orders.append(sell_order)

    def _cancel_order(self, order: dict):
        """取消订单"""
        # 在实际实现中，这里会调用交易所API取消订单
        pass

    def on_stop(self):
        # 撤销所有订单
        for order in self.grid_orders:
            self._cancel_order(order)
        self.grid_orders = []
        super().on_stop()
