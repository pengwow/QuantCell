# -*- coding: utf-8 -*-
"""
简单双均线策略（基于 axond 体系）

使用 axond.AxonStrategy 实现的经典双均线策略示例。
展示：
1. 继承 AxonStrategy
2. 重写 on_bar() 实现交易逻辑
3. 使用 buy/sell 下单接口
4. 配置驱动参数

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from axond.axon_strategy import AxonStrategy
from axond.strategy_config import StrategyConfig
from axond.types import Bar, InstrumentId


class SimpleDualMAStrategy(AxonStrategy):
    """
    简单双均线策略

    当快线从下方穿越慢线时买入（金叉）
    当快线从上方穿越慢线时卖出（死叉）

    Args:
        config: 策略配置，必须包含 fast_period 和 slow_period

    Examples:
        >>> config = StrategyConfig(
        ...     instrument_ids=[InstrumentId("BTCUSDT", "binance")],
        ...     bar_types=["1h"],
        ...     trade_size=Decimal("0.1"),
        ... )
        >>> strategy = SimpleDualMAStrategy(config, fast_period=10, slow_period=30)
    """

    def __init__(
        self,
        config: StrategyConfig,
        fast_period: int = 10,
        slow_period: int = 30,
    ) -> None:
        """初始化双均线策略

        Args:
            config: 策略配置
            fast_period: 快线周期
            slow_period: 慢线周期
        """
        super().__init__(config)

        if fast_period <= 0 or slow_period <= 0:
            raise ValueError("fast_period 和 slow_period 必须大于 0")
        if fast_period >= slow_period:
            raise ValueError("fast_period 必须小于 slow_period")

        # 策略参数
        self.fast_period = fast_period
        self.slow_period = slow_period

        # K 线缓存（用于计算均线）
        self._close_prices: List[float] = []
        self._max_cache_size = slow_period + 1

        # 上一次的均线状态（用于检测交叉）
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

        # 数据不足时无法计算均线
        if len(self._close_prices) < self._slow_period:
            return

        # 计算快慢均线
        fast_ma = self._calculate_ma(self._fast_period)
        slow_ma = self._calculate_ma(self._slow_period)

        # 当前快线在慢线上方
        fast_above_slow = fast_ma > slow_ma

        # 检测交叉
        if self._prev_fast_above_slow is None:
            # 第一次运行，初始化状态
            self._prev_fast_above_slow = fast_above_slow
            return

        if self._prev_fast_above_slow and not fast_above_slow:
            # 死叉：快线跌破慢线，卖出
            symbol = self.config.instrument_ids[0].symbol
            self.log_info(f"死叉信号，快线={fast_ma:.2f}, 慢线={slow_ma:.2f}")
            self.close_position(symbol)
        elif not self._prev_fast_above_slow and fast_above_slow:
            # 金叉：快线上穿慢线，买入
            symbol = self.config.instrument_ids[0].symbol
            self.log_info(f"金叉信号，快线={fast_ma:.2f}, 慢线={slow_ma:.2f}")
            self.buy(symbol)

        # 更新状态
        self._prev_fast_above_slow = fast_above_slow

    def _calculate_ma(self, period: int) -> float:
        """计算最近 period 期的简单移动平均

        Args:
            period: 周期

        Returns:
            MA 值
        """
        if len(self._close_prices) < period:
            return 0.0
        return sum(self._close_prices[-period:]) / period
