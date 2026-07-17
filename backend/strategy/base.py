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
             新增字段(2026-07-17 funding arbitrage 升级)：
             - spot_* : 现货腿支持
             - funding_cash : funding 现金流累计
             - settle_funding() : funding 结算入口
             - account_equity : 账户净值(策略层用)
             - last_funding_rate/time : 最近 funding 状态
    """
    symbol: str
    closes: list[float] = field(default_factory=list)
    positions: dict[str, float] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)

    # —— 新增：现货腿支持（2026-07-17 funding arbitrage 升级）——
    spot_symbol: str = ""
    spot_close: float = 0.0
    spot_volume: float = 0.0
    spot_target_position: float = 0.0  # 现货目标仓位（策略 set, baseline 读）

    # —— 新增：funding 现金流 ——
    funding_cash: float = 0.0
    last_funding_rate: float = 0.0
    last_funding_time: int = 0
    funding_cash_settlement_enabled: bool = True

    # —— 新增：账户净值(策略层算 notional 用)——
    account_equity: float = 0.0

    def settle_funding(
        self,
        funding_rate: float,
        funding_time: int,
        position_notional: float,
    ) -> float:
        """funding 结算入口(实现见 Task 3)。

        本任务只占位, Task 3 替换为完整实现。
        """
        return 0.0


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
