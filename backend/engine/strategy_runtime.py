# -*- coding: utf-8 -*-
"""StrategyRuntime — 策略运行时数据类"""

from __future__ import annotations

import time
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
        started_at: 启动时间戳（time.monotonic()）
        order_count: 已下订单数
        fill_count: 成交数
        rejected_count: 风控拒绝数
        last_action: 最后动作类型（buy/sell/hold）
        last_price: 最后处理价格
        realized_pnl: 已实现 PnL（初版固定 0.0）
        mode: 运行模式（paper/live/backtest）
        strategy_name: 策略模板名
        params: 策略参数字典
    """
    strategy_id: str
    strategy: Any
    symbols: list[str]
    status: str = "stopped"
    loop: Optional[Any] = None
    started_at: float = 0.0
    order_count: int = 0
    fill_count: int = 0
    rejected_count: int = 0
    last_action: Optional[str] = None
    last_price: float = 0.0
    realized_pnl: float = 0.0
    mode: str = "paper"
    strategy_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 响应字典"""
        duration = time.monotonic() - self.started_at if self.started_at > 0 else 0
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbols": self.symbols,
            "status": self.status,
            "mode": self.mode,
            "started_at": self.started_at,
            "duration_secs": round(duration, 1),
            "order_count": self.order_count,
            "fill_count": self.fill_count,
            "rejected_count": self.rejected_count,
            "last_action": self.last_action,
            "last_price": self.last_price,
            "realized_pnl": self.realized_pnl,
        }
