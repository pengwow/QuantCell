# -*- coding: utf-8 -*-
"""基础策略类 — 基于 axon_quant"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from axon_quant import Action
from backtest.backtest_loop import RuleStrategy
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class BaseStrategy(RuleStrategy):
    """基础策略类，使用 axon_quant Action 体系"""

    def __init__(self, params: dict = None):
        self._params = params or {}
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

    def buy(self, symbol: str = None, quantity: float = None) -> Action:
        qty = quantity or self._params.get("trade_size", 0.1)
        self._position_side = "long"
        return Action("buy", 0.8, qty, "base_strategy", 0)

    def sell(self, symbol: str = None, quantity: float = None) -> Action:
        qty = quantity or self._params.get("trade_size", 0.1)
        self._position_side = "short"
        return Action("sell", 0.8, qty, "base_strategy", 0)

    def close_position(self, symbol: str = None) -> Action:
        self._position_side = "flat"
        return Action("sell", 0.9, 0.0, "base_strategy", 0)

    def is_flat(self, symbol: str = None) -> bool:
        return self._position_side == "flat"

    def is_long(self, symbol: str = None) -> bool:
        return self._position_side == "long"

    def is_short(self, symbol: str = None) -> bool:
        return self._position_side == "short"
