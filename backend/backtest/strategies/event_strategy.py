# -*- coding: utf-8 -*-
"""事件驱动策略基类 — 基于 axon_quant 体系"""

from __future__ import annotations

import datetime as dt
from abc import abstractmethod
from typing import Any, Optional, List

from axon_bridge import Action
from backtest.backtest_loop import RuleStrategy
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class EventDrivenStrategyConfig:
    """事件驱动策略配置"""

    def __init__(
        self,
        symbols: List[str],
        trade_size: float = 0.1,
        log_level: str = "INFO",
    ):
        if not symbols:
            raise ValueError("symbols 不能为空")
        self.symbols = symbols
        self.symbol = symbols[0]
        self.trade_size = trade_size
        self.log_level = log_level


class EventDrivenStrategy(RuleStrategy):
    """事件驱动策略基类

    子类实现 _on_bar_impl() 处理K线数据。
    """

    def __init__(self, config: EventDrivenStrategyConfig) -> None:
        self.event_config = config
        self.bars_processed: int = 0
        self.start_time: Optional[dt.datetime] = None
        self.end_time: Optional[dt.datetime] = None
        self._position_side: str = "flat"

    def on_start(self) -> None:
        self.start_time = dt.datetime.now()
        logger.info(f"策略启动时间: {self.start_time}")

    def on_bar(self, bar: dict) -> Action:
        self.bars_processed += 1
        return self._on_bar_impl(bar)

    @abstractmethod
    def _on_bar_impl(self, bar: dict) -> Action:
        ...

    def on_stop(self) -> None:
        self.end_time = dt.datetime.now()
        duration = self.end_time - self.start_time if self.start_time else None
        logger.info(f"策略停止: 处理 {self.bars_processed} 根K线, 耗时 {duration}")

    def buy(self, symbol: Optional[str] = None, quantity: Optional[float] = None) -> Action:
        target = symbol or self.event_config.symbol
        qty = quantity or self.event_config.trade_size
        self._position_side = "long"
        return Action("buy", 0.8, qty, "event_strategy", 0)

    def sell(self, symbol: Optional[str] = None, quantity: Optional[float] = None) -> Action:
        target = symbol or self.event_config.symbol
        qty = quantity or self.event_config.trade_size
        self._position_side = "short"
        return Action("sell", 0.8, qty, "event_strategy", 0)

    def close_position(self, symbol: Optional[str] = None) -> Action:
        self._position_side = "flat"
        return Action("sell", 0.9, 0.0, "event_strategy", 0)

    def get_position_size(self, symbol: Optional[str] = None) -> float:
        if self._position_side == "long":
            return self.event_config.trade_size
        elif self._position_side == "short":
            return -self.event_config.trade_size
        return 0.0

    def is_flat(self, symbol: Optional[str] = None) -> bool:
        return self._position_side == "flat"

    def is_long(self, symbol: Optional[str] = None) -> bool:
        return self._position_side == "long"

    def is_short(self, symbol: Optional[str] = None) -> bool:
        return self._position_side == "short"
