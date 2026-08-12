# -*- coding: utf-8 -*-
"""回测策略适配器

将策略接口适配到 axon_quant 回测引擎。
策略脚本继承此适配器，可以在回测环境中运行。
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional

from axon_bridge import Action
from backtest.backtest_loop import RuleStrategy
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class StrategyConfig:
    """策略配置基类"""

    def __init__(
        self,
        symbols: list[str],
        trade_size: float = 0.1,
        **kwargs,
    ):
        self.symbols = symbols
        self.symbol = symbols[0] if symbols else ""
        self.trade_size = trade_size
        for k, v in kwargs.items():
            setattr(self, k, v)


class StrategyAdapter(RuleStrategy):
    """回测策略适配器基类

    子类实现 _on_bar_impl() 处理K线数据。
    """

    def __init__(self, config: StrategyConfig) -> None:
        self._config = config
        self._position_side: str = "flat"
        self.bars_processed: int = 0

    def on_start(self) -> None:
        pass

    def on_bar(self, bar: dict) -> Action:
        self.bars_processed += 1
        return self._on_bar_impl(bar)

    @abstractmethod
    def _on_bar_impl(self, bar: dict) -> Action:
        ...

    def on_stop(self) -> None:
        pass

    def buy(self, symbol: Optional[str] = None, quantity: Optional[float] = None) -> Action:
        target = symbol or self._config.symbol
        qty = quantity or self._config.trade_size
        self._position_side = "long"
        return Action("buy", 0.8, qty, "adapter", 0)

    def sell(self, symbol: Optional[str] = None, quantity: Optional[float] = None) -> Action:
        target = symbol or self._config.symbol
        qty = quantity or self._config.trade_size
        self._position_side = "short"
        return Action("sell", 0.8, qty, "adapter", 0)

    def close_position(self, symbol: Optional[str] = None) -> Action:
        self._position_side = "flat"
        return Action("sell", 0.9, 0.0, "adapter", 0)

    def is_flat(self, symbol: Optional[str] = None) -> bool:
        return self._position_side == "flat"

    def is_long(self, symbol: Optional[str] = None) -> bool:
        return self._position_side == "long"

    def is_short(self, symbol: Optional[str] = None) -> bool:
        return self._position_side == "short"
