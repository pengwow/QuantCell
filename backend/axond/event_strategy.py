# -*- coding: utf-8 -*-
"""事件驱动策略基类"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any

from axond.axon_strategy import AxonStrategy
from axond.types import Bar


class EventDrivenStrategy(AxonStrategy):
    """事件驱动策略基类。

    子类应实现 _on_bar_impl() 方法。

    Examples::

        class MyStrategy(EventDrivenStrategy):
            def _on_bar_impl(self, bar):
                if bar.close > 100:
                    self.buy(bar.instrument_id.symbol, 0.1, bar.close)
    """

    def on_bar(self, bar: Bar) -> None:
        """收到 K 线数据，调用子类实现。"""
        self.bars_processed += 1
        self._on_bar_impl(bar)

    @abstractmethod
    def _on_bar_impl(self, bar: Bar) -> None:
        """K 线处理实现（子类必须实现）。"""
        raise NotImplementedError
