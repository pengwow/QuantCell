"""策略模板基类 — 8 策略模板统一接口。

ponytail: 8 模板都继承 BaseStrategy, 统一 on_bar(bar, ctx) -> Action 签名
         模板只关心策略逻辑, 不感知账户/凭证/交易所
         ctx 是 StrategyContext, 提供历史数据/账户/订单簿访问
"""
from __future__ import annotations

import math
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

    字段:
    - spot_* : 现货腿支持 (funding_arbitrage 用, baseline 读 spot_target_position)
    - account_equity : 账户净值(策略层算 notional 用)

    DEPRECATED 字段(2026-07-18 axon_quant 0.6.0 升级后保留读接口):
    - funding_cash / settle_funding: 完全下沉到 axon_quant 引擎的
      RunResult.total_funding_pnl, 策略层不再调用
    - funding_cash_settlement_enabled 默认 False
    - last_funding_rate / last_funding_time 保留为只读 0
    """
    symbol: str
    closes: list[float] = field(default_factory=list)
    positions: dict[str, float] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)

    # —— 现货腿支持 (funding_arbitrage 用) ——
    spot_symbol: str = ""
    spot_close: float = 0.0
    spot_volume: float = 0.0
    spot_target_position: float = 0.0  # 现货目标仓位(策略 set, baseline 读)

    # —— 账户净值(策略层算 notional 用)——
    account_equity: float = 0.0

    # —— DEPRECATED 字段(2026-07-18 axon_quant 0.6.0 升级后保留读接口)——
    # funding cash 已完全下沉到 axon_quant 引擎的 RunResult.total_funding_pnl,
    # 策略层不再调用 settle_funding()。这些字段保留读接口以避免破坏外部代码,
    # 默认值 0,settle_funding() 改为 no-op 返回 0.0。
    funding_cash: float = 0.0  # DEPRECATED: 始终为 0
    last_funding_rate: float = 0.0  # DEPRECATED
    last_funding_time: int = 0  # DEPRECATED
    funding_cash_settlement_enabled: bool = False  # DEPRECATED, 默认 False

    def settle_funding(
        self,
        funding_rate: float,
        funding_time: int,
        position_notional: float,
    ) -> float:
        """DEPRECATED: funding cash 已下沉到 axon_quant 引擎 (RunResult.total_funding_pnl)。

        保留作 no-op 接口以避免破坏外部调用, 返回 0.0。
        业务代码不应再调用此方法, 由 axon_quant.backtest.BacktestEngine.push_funding() 替代。
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
