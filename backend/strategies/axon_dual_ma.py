# -*- coding: utf-8 -*-
"""双均线交叉策略（axon 版本）

使用 AxonStrategy 基类，不依赖 axon_quant。
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from decimal import Decimal
from typing import List

from axond.axon_strategy import AxonStrategy
from axond.strategy_config import StrategyConfig
from axond.types import Bar, InstrumentId, OrderType


@dataclass
class DualEMACrossoverConfig(StrategyConfig):
    """双均线交叉策略配置"""
    fast_period: int = 10
    slow_period: int = 20


class DualEMACrossover(AxonStrategy):
    """双均线交叉策略：快线穿慢线产生交易信号

    当快线（短期EMA）上穿慢线（长期EMA）时买入，
    当快线下穿慢线时卖出。
    """

    def __init__(self, config: DualEMACrossoverConfig):
        if config.fast_period >= config.slow_period:
            raise ValueError(f"快线周期({config.fast_period})必须小于慢线周期({config.slow_period})")
        super().__init__(config)
        self.fast_prices: List[float] = []
        self.slow_prices: List[float] = []
        self.position_held = False

    def on_start(self):
        super().on_start()
        self.fast_prices = []
        self.slow_prices = []
        self.position_held = False

    def on_bar(self, bar: Bar):
        super().on_bar(bar)

        # 收集价格数据
        self.fast_prices.append(bar.close)
        self.slow_prices.append(bar.close)

        # 等待足够的数据
        if len(self.slow_prices) < self.config.slow_period:
            return

        # 计算EMA
        fast_ema = self._calculate_ema(self.fast_prices[-self.config.fast_period:], self.config.fast_period)
        slow_ema = self._calculate_ema(self.slow_prices[-self.config.slow_period:], self.config.slow_period)

        symbol = bar.instrument_id.symbol
        pos_size = self.get_position_size(symbol)

        # 金叉：快线上穿慢线，买入
        if fast_ema > slow_ema and not self.position_held:
            if pos_size < 0:
                self.close_position(symbol)
            self.buy(symbol, float(self.config.trade_size), bar.close)
            self.position_held = True

        # 死叉：快线下穿慢线，卖出
        elif fast_ema < slow_ema and self.position_held:
            if pos_size > 0:
                self.close_position(symbol)
            self.sell(symbol, float(self.config.trade_size), bar.close)
            self.position_held = False

    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """计算指数移动平均线"""
        if len(prices) < period:
            return prices[-1] if prices else 0.0

        prices_array = np.array(prices)
        multiplier = 2 / (period + 1)

        ema = prices_array[0]
        for price in prices_array[1:]:
            ema = (price - ema) * multiplier + ema

        return ema
