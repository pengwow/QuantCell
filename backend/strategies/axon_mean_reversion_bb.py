# -*- coding: utf-8 -*-
"""均值回归布林带策略（axon 版本）

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
class MeanReversionBBConfig(StrategyConfig):
    """均值回归布林带策略配置"""
    bb_period: int = 20
    bb_std_dev: float = 2.0
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70


class MeanReversionBB(AxonStrategy):
    """均值回归布林带策略

    使用布林带和RSI指标进行均值回归交易：
    - 当价格触及布林带下轨且RSI超卖时买入
    - 当价格触及布林带上轨且RSI超买时卖出
    """

    def __init__(self, config: MeanReversionBBConfig):
        if config.bb_period <= 0:
            raise ValueError(f"bb_period必须大于0，得到{config.bb_period}")
        if config.bb_std_dev <= 0:
            raise ValueError(f"bb_std_dev必须大于0，得到{config.bb_std_dev}")
        if config.rsi_period <= 0:
            raise ValueError(f"rsi_period必须大于0，得到{config.rsi_period}")
        if config.rsi_oversold >= config.rsi_overbought:
            raise ValueError(f"rsi_oversold({config.rsi_oversold})必须小于rsi_overbought({config.rsi_overbought})")
        super().__init__(config)
        self.prices: List[float] = []
        self.position_held = False

    def on_start(self):
        super().on_start()
        self.prices = []
        self.position_held = False

    def on_bar(self, bar: Bar):
        super().on_bar(bar)
        self.prices.append(bar.close)

        if len(self.prices) < self.config.bb_period:
            return

        prices_array = np.array(self.prices[-self.config.bb_period:])

        # 计算布林带
        sma = np.mean(prices_array)
        std = np.std(prices_array)
        upper_band = sma + self.config.bb_std_dev * std
        lower_band = sma - self.config.bb_std_dev * std

        # 计算RSI
        rsi = self._calculate_rsi(np.array(self.prices), self.config.rsi_period)

        symbol = bar.instrument_id.symbol
        pos_size = self.get_position_size(symbol)

        # 买入条件：价格触及下轨且RSI超卖
        if bar.close <= lower_band and rsi < self.config.rsi_oversold:
            if not self.position_held:
                if pos_size < 0:
                    self.close_position(symbol)
                self.buy(symbol, float(self.config.trade_size), bar.close)
                self.position_held = True

        # 卖出条件：价格触及上轨且RSI超买
        elif bar.close >= upper_band and rsi > self.config.rsi_overbought:
            if not self.position_held:
                if pos_size > 0:
                    self.close_position(symbol)
                self.sell(symbol, float(self.config.trade_size), bar.close)
                self.position_held = True

        # 平仓条件：价格回归中轨
        elif self.position_held:
            if pos_size > 0 and bar.close >= sma:
                self.close_position(symbol)
                self.position_held = False
            elif pos_size < 0 and bar.close <= sma:
                self.close_position(symbol)
                self.position_held = False

    def _calculate_rsi(self, prices: np.ndarray, period: int) -> float:
        """计算RSI"""
        if len(prices) < period + 1:
            return 50.0

        deltas = np.diff(prices[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
