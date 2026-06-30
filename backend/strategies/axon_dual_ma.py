# -*- coding: utf-8 -*-
"""双均线交叉策略（axon 版本）

使用 AxonStrategy 基类，不依赖 axon_quant。
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

from axond.axon_strategy import AxonStrategy
from axond.strategy_config import StrategyConfig
from axond.types import Bar, InstrumentId, OrderType


@dataclass
class DualEMACrossoverConfig(StrategyConfig):
    """双均线交叉策略配置

    默认 trade_size=0.001(适配 BTC/ETH 等高单价品种,单笔名义约 100 USDT),
    避免默认 1.0 时单笔 notional 过大(>10 万 USDT)触发 cash 校验拒单,
    也避免手续费异常累积(1 BTC × 0.001 fee × 频繁交易 = 数十万 USDT 手续费)。
    大账户回测可通过 -p '{"trade_size": 1.0}' 显式覆盖。
    """
    fast_period: int = 10
    slow_period: int = 20
    # 单笔交易数量:0.001 BTC/ETH ≈ 100 USDT 名义价值,匹配小账户回测规模
    trade_size: Decimal = field(default_factory=lambda: Decimal("0.001"))


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

    def on_start(self, context=None):
        super().on_start(context)
        self.fast_prices = []
        self.slow_prices = []
        self.position_held = False

    def on_bar(self, bar: Bar, context=None):
        super().on_bar(bar)

        # 收集价格数据
        self.fast_prices.append(bar.close)
        self.slow_prices.append(bar.close)

        # 等待足够的数据
        if len(self.slow_prices) < self.config.slow_period:
            return []

        # 计算EMA
        fast_ema = self._calculate_ema(self.fast_prices[-self.config.fast_period:], self.config.fast_period)
        slow_ema = self._calculate_ema(self.slow_prices[-self.config.slow_period:], self.config.slow_period)

        # 兼容两种 Bar 风格：
        # - strategy.core.Bar（str symbol 字段）
        # - axond.types.Bar（InstrumentId instrument_id 字段）
        if hasattr(bar, "instrument_id") and getattr(bar, "instrument_id", None) is not None:
            symbol = bar.instrument_id.symbol
        else:
            symbol = bar.symbol
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

        # 返回 axond 风格 dict order 列表(由 backtest_loop 适配为 Order 对象
        # 推给 axon_quant 撮合引擎),并清空避免下一 bar 重复推
        pending = list(self._orders)
        self._orders.clear()
        return pending

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
