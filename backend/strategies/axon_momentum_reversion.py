# -*- coding: utf-8 -*-
"""动量与均值回归混合策略（axon 版本）

使用 AxonStrategy 基类，不依赖 nautilus_trader。
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
class MomentumReversionConfig(StrategyConfig):
    """动量与均值回归混合策略配置"""
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_period: int = 14
    rsi_overbought: int = 70
    rsi_oversold: int = 30


class MomentumReversion(AxonStrategy):
    """动量与均值回归混合策略
    
    逻辑：
    1. 使用MACD作为趋势方向判断指标
    2. 使用RSI作为入场时机确认指标
    3. 当MACD显示上升趋势且RSI从超卖区域向上突破时，做多
    4. 当MACD显示下降趋势且RSI从超买区域向下突破时，做空
    5. 持仓后，当趋势反转信号出现时平仓
    """

    def __init__(self, config: MomentumReversionConfig):
        if config.macd_fast >= config.macd_slow:
            raise ValueError(f"MACD快线周期({config.macd_fast})必须小于慢线周期({config.macd_slow})")
        if config.rsi_oversold >= config.rsi_overbought:
            raise ValueError(f"RSI超卖线({config.rsi_oversold})必须小于超买线({config.rsi_overbought})")
        super().__init__(config)
        self.prices: List[float] = []
        self.prev_rsi: float = 0.0
        self.position_held = False

    def on_start(self):
        super().on_start()
        self.prices = []
        self.prev_rsi = 0.0
        self.position_held = False

    def on_bar(self, bar: Bar):
        super().on_bar(bar)
        self.prices.append(bar.close)

        if len(self.prices) < self.config.macd_slow + self.config.macd_signal:
            return

        prices_array = np.array(self.prices)
        
        # 计算MACD
        macd_line, signal_line = self._calculate_macd(
            prices_array,
            self.config.macd_fast,
            self.config.macd_slow,
            self.config.macd_signal,
        )
        
        # 计算RSI
        rsi = self._calculate_rsi(prices_array, self.config.rsi_period)
        
        symbol = bar.instrument_id.symbol
        pos_size = self.get_position_size(symbol)
        
        # 做多条件：MACD金叉且RSI从超卖区域向上突破
        if macd_line > signal_line and self.prev_rsi < self.config.rsi_oversold and rsi >= self.config.rsi_oversold:
            if not self.position_held:
                if pos_size < 0:
                    self.close_position(symbol)
                self.buy(symbol, float(self.config.trade_size), bar.close)
                self.position_held = True
        
        # 做空条件：MACD死叉且RSI从超买区域向下突破
        elif macd_line < signal_line and self.prev_rsi > self.config.rsi_overbought and rsi <= self.config.rsi_overbought:
            if not self.position_held:
                if pos_size > 0:
                    self.close_position(symbol)
                self.sell(symbol, float(self.config.trade_size), bar.close)
                self.position_held = True
        
        # 平仓条件：趋势反转
        elif self.position_held:
            if pos_size > 0 and macd_line < signal_line:
                self.close_position(symbol)
                self.position_held = False
            elif pos_size < 0 and macd_line > signal_line:
                self.close_position(symbol)
                self.position_held = False
        
        self.prev_rsi = rsi

    def _calculate_macd(self, prices: np.ndarray, fast: int, slow: int, signal: int):
        """计算MACD"""
        fast_ema = self._ema(prices, fast)
        slow_ema = self._ema(prices, slow)
        macd_line = fast_ema - slow_ema
        signal_line = self._ema(np.array([macd_line]), signal)
        return macd_line, signal_line

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

    def _ema(self, data: np.ndarray, period: int) -> float:
        """计算EMA"""
        if len(data) < period:
            return data[-1] if len(data) > 0 else 0.0
        
        multiplier = 2 / (period + 1)
        ema = data[0]
        for value in data[1:]:
            ema = (value - ema) * multiplier + ema
        return ema
