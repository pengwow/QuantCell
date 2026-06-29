# -*- coding: utf-8 -*-
"""
测试策略 test0001（基于 axond 体系）

这是一个用于演示和测试的简单策略。
使用价格突破 N 日高点买入、跌破 N 日低点卖出的策略逻辑。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Deque, Optional

from axond.axon_strategy import AxonStrategy
from axond.strategy_config import StrategyConfig
from axond.types import Bar


class Test0001Strategy(AxonStrategy):
    """
    测试策略 test0001

    价格突破策略：
    - 当收盘价突破 N 日最高价时，买入
    - 当收盘价跌破 N 日最低价时，卖出

    Args:
        config: 策略配置
        lookback_period: 回看周期，默认 20

    Examples:
        >>> config = StrategyConfig(
        ...     instrument_ids=[InstrumentId("BTCUSDT", "binance")],
        ...     bar_types=["1h"],
        ...     trade_size=Decimal("0.1"),
        ... )
        >>> strategy = Test0001Strategy(config, lookback_period=20)
    """

    def __init__(
        self,
        config: StrategyConfig,
        lookback_period: int = 20,
    ) -> None:
        """初始化测试策略"""
        super().__init__(config)

        if lookback_period <= 0:
            raise ValueError("lookback_period 必须大于 0")

        self.lookback_period = lookback_period

        # K 线缓存
        self._closes: Deque[float] = deque(maxlen=lookback_period + 1)

    def on_start(self) -> None:
        """策略启动时清空缓存"""
        super().on_start()
        self._closes.clear()

    def on_bar(self, bar: Bar) -> None:
        """处理 K 线数据"""
        super().on_bar(bar)

        # 累积数据
        self._closes.append(bar.close)

        # 数据不足
        if len(self._closes) <= self.lookback_period:
            return

        # 计算回看期内的最高价和最低价（不含当前 bar）
        recent_closes = list(self._closes)[: -1]  # 排除当前 bar
        period_high = max(recent_closes)
        period_low = min(recent_closes)

        symbol = self.config.instrument_ids[0].symbol

        # 突破最高价：买入
        if bar.close > period_high:
            self.log_info(
                f"突破最高价: close={bar.close:.2f}, period_high={period_high:.2f}"
            )
            self.buy(symbol)

        # 跌破最低价：卖出
        elif bar.close < period_low:
            self.log_info(
                f"跌破最低价: close={bar.close:.2f}, period_low={period_low:.2f}"
            )
            self.close_position(symbol)
