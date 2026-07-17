"""策略模板基类 — 8 策略模板统一接口。

ponytail: 8 模板都继承 BaseStrategy, 统一 on_bar(bar, ctx) -> Action 签名
         模板只关心策略逻辑, 不感知账户/凭证/交易所
         ctx 是 StrategyContext, 提供历史数据/账户/订单簿访问
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from axon_bridge import Action


@dataclass
class StrategyConfig:
    """策略通用配置。"""
    name: str
    symbol: str = "BTCUSDT"
    interval: float = 1.0
    position_limit: float = 0.1
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyContext:
    """策略运行上下文。

    ponytail: 简洁接口, 模板只关心 closes/positions/orders
             不感知具体交易所/账户细节
    """
    symbol: str
    closes: list[float] = field(default_factory=list)
    positions: dict[str, float] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)


class BaseStrategy(ABC):
    """所有 8 策略模板继承此类。"""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self._ctx: StrategyContext | None = None

    def on_start(self, ctx: StrategyContext) -> None:
        """可选：启动钩子（重置内部状态）。"""
        self._ctx = ctx

    @abstractmethod
    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        """必须实现：每根 K 线返回 Action。"""

    def on_fill(self, fill: dict, ctx: StrategyContext) -> None:
        """可选：成交回调。"""

    def on_stop(self, ctx: StrategyContext) -> None:
        """可选：停止钩子。"""
