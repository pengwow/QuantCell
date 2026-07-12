# -*- coding: utf-8 -*-
"""StrategyRuntime — 策略运行时数据类"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StrategyRuntime:
    """策略运行时数据类

    Attributes:
        strategy_id: 策略 ID
        strategy: 策略实例（实现 on_bar → Action）
        symbols: 交易对列表
        status: 策略状态 (stopped/running/paused/error)
        loop: StrategyLoop 实例（实盘时使用）
    """
    strategy_id: str
    strategy: Any
    symbols: list[str]
    status: str = "stopped"
    loop: Optional[Any] = None
