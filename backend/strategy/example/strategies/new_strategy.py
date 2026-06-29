# -*- coding: utf-8 -*-
"""
新策略示例（基于 axond 体系）

展示如何创建自定义策略类，基于 axond.AxonStrategy 实现。
这是一个多因子综合策略示例。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from axond.axon_strategy import AxonStrategy
from axond.strategy_config import StrategyConfig
from axond.types import Bar


class NewStrategy(AxonStrategy):
    """
    新策略示例

    基于均线交叉 + RSI 过滤的多因子策略：
    - 买入条件：快线上穿慢线 + RSI < 超买阈值
    - 卖出条件：快线下穿慢线 或 RSI > 超买阈值

    Args:
        config: 策略配置
        fast_period: 快线周期，默认 5
        slow_period: 慢线周期，默认 20
        rsi_period: RSI 周期，默认 14
        rsi_overbought: RSI 超买阈值，默认 70
        rsi_oversold: RSI 超卖阈值，默认 30

    Examples:
        >>> config = StrategyConfig(
        ...     instrument_ids=[InstrumentId("BTCUSDT", "binance")],
        ...     bar_types=["1h"],
        ...     trade_size=Decimal("0.1"),
        ... )
        >>> strategy = NewStrategy(config)
    """

    def __init__(
        self,
        config: StrategyConfig,
        fast_period: int = 5,
        slow_period: int = 20,
        rsi_period: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
    ) -> None:
        """初始化新策略"""
        super().__init__(config)

        # 参数验证
        if fast_period <= 0 or slow_period <= 0 or rsi_period <= 0:
            raise ValueError("周期参数必须大于 0")
        if fast_period >= slow_period:
            raise ValueError("fast_period 必须小于 slow_period")
        if not (0 < rsi_oversold < rsi_overbought < 100):
            raise ValueError("RSI 阈值不合法")

        # 策略参数
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

        # K 线缓存
        self._close_prices: List[float] = []
        self._max_cache_size = max(slow_period, rsi_period * 2) + 1

        # 状态变量
        self._prev_fast_above_slow: Optional[bool] = None

    def on_start(self) -> None:
        """策略启动时清空缓存"""
        super().on_start()
        self._close_prices.clear()
        self._prev_fast_above_slow = None

    def on_bar(self, bar: Bar) -> None:
        """处理 K 线数据"""
        super().on_bar(bar)

        # 累积收盘价
        self._close_prices.append(bar.close)
        if len(self._close_prices) > self._max_cache_size:
            self._close_prices.pop(0)

        # 数据不足
        if len(self._close_prices) < self._slow_period:
            return

        # 计算指标
        fast_ma = self._calculate_ma(self.fast_period)
        slow_ma = self._calculate_ma(self.slow_period)
        rsi = self._calculate_rsi(self.rsi_period)

        # 当前状态
        fast_above_slow = fast_ma > slow_ma

        # 第一次运行
        if self._prev_fast_above_slow is None:
            self._prev_fast_above_slow = fast_above_slow
            return

        symbol = self.config.instrument_ids[0].symbol

        # 金叉 + RSI 不超买 → 买入
        if not self._prev_fast_above_slow and fast_above_slow and rsi < self.rsi_overbought:
            self.log_info(
                f"金叉买入信号: fast={fast_ma:.2f}, slow={slow_ma:.2f}, RSI={rsi:.2f}"
            )
            self.buy(symbol)

        # 死叉 或 RSI 超买 → 卖出
        elif (self._prev_fast_above_slow and not fast_above_slow) or rsi > self.rsi_overbought:
            self.log_info(
                f"卖出信号: fast={fast_ma:.2f}, slow={slow_ma:.2f}, RSI={rsi:.2f}"
            )
            self.close_position(symbol)

        # 更新状态
        self._prev_fast_above_slow = fast_above_slow

    def _calculate_ma(self, period: int) -> float:
        """计算简单移动平均"""
        if len(self._close_prices) < period:
            return 0.0
        return sum(self._close_prices[-period:]) / period

    def _calculate_rsi(self, period: int) -> float:
        """计算 RSI 指标

        Args:
            period: RSI 周期

        Returns:
            RSI 值（0-100）
        """
        if len(self._close_prices) < period + 1:
            return 50.0  # 数据不足返回中性值

        gains: List[float] = []
        losses: List[float] = []

        # 计算价格变化
        recent_prices = self._close_prices[-(period + 1):]
        for i in range(1, len(recent_prices)):
            change = recent_prices[i] - recent_prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(-change)

        avg_gain = sum(gains) / period if gains else 0.0
        avg_loss = sum(losses) / period if losses else 0.0

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi
