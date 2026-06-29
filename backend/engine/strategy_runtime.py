# -*- coding: utf-8 -*-
"""StrategyRuntime — 策略运行时数据类

存储策略运行时状态，包括策略实例、交易对、状态和循环引用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from strategy.core.unified_strategy import UnifiedStrategy


@dataclass
class StrategyRuntime:
    """策略运行时数据类

    Attributes:
        strategy_id: 策略 ID
        strategy: 策略实例
        symbols: 交易对列表
        status: 策略状态 (stopped/running/paused/error)
        loop: StrategyLoop 实例（实盘时使用）
    """
    strategy_id: str
    strategy: UnifiedStrategy
    symbols: list[str]
    status: str = "stopped"
    loop: Optional[Any] = None
