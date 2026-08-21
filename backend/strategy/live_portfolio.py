"""LivePortfolio — 实盘持仓/资金追踪

axon_quant 没有提供 Python 级别的实时 Portfolio 类（仅 backtest 引擎有），
因此 QuantCell 自建轻量持仓追踪器，提供:
  - 实时资金/持仓/盈亏计算
  - 订单 → 成交 → 持仓的状态机
  - 线程安全（StrategyLoop 单线程运行，无需复杂锁）

设计上对齐 axon_quant.backtest 的 BacktestResult 字段名，方便回测/实盘统一分析。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """单品种持仓。"""

    symbol: str
    quantity: float = 0.0  # 合约数量(正=多, 负=空)
    avg_price: float = 0.0  # 平均开仓价
    realized_pnl: float = 0.0  # 已实现盈亏
    unrealized_pnl: float = 0.0  # 未实现盈亏(按当前价算)
    side: str = "flat"  # flat / long / short

    def update_on_fill(self, side: str, qty: float, price: float) -> None:
        """成交后更新持仓。"""
        signed = qty if side.lower() == "buy" else -qty
        new_qty = self.quantity + signed

        if self.quantity == 0:
            # 新开仓
            self.avg_price = price
            self.quantity = new_qty
        elif (self.quantity > 0 and signed > 0) or (self.quantity < 0 and signed < 0):
            # 加仓: 更新均价
            total_cost = self.avg_price * abs(self.quantity) + price * abs(signed)
            self.quantity = new_qty
            self.avg_price = total_cost / abs(self.quantity) if self.quantity != 0 else 0.0
        else:
            # 减仓或反手
            close_qty = min(abs(signed), abs(self.quantity))
            close_pnl = (price - self.avg_price) * close_qty
            # 平多(quantity>0): profit = (sell_price - avg) * qty, 已经正确
            # 平空(quantity<0): profit = (avg - buy_price) * qty, 需要翻转符号
            if self.quantity < 0:
                close_pnl = -close_pnl
            self.realized_pnl += close_pnl

            remaining = abs(signed) - close_qty
            if remaining > 0:
                # 反手
                self.quantity = new_qty
                self.avg_price = price
            else:
                self.quantity = new_qty
                if self.quantity == 0:
                    self.avg_price = 0.0

        # 更新方向
        if self.quantity > 0:
            self.side = "long"
        elif self.quantity < 0:
            self.side = "short"
        else:
            self.side = "flat"

    def mark_to_market(self, current_price: float) -> None:
        """按当前价计算未实现盈亏。"""
        if self.quantity == 0:
            self.unrealized_pnl = 0.0
            return
        if self.side == "long":
            self.unrealized_pnl = (current_price - self.avg_price) * self.quantity
        elif self.side == "short":
            self.unrealized_pnl = (self.avg_price - current_price) * abs(self.quantity)
        else:
            self.unrealized_pnl = 0.0


@dataclass
class LivePortfolio:
    """实盘持仓/资金追踪器。

    用法:
        portfolio = LivePortfolio(initial_cash=100_000)
        portfolio.update_on_fill(symbol, "buy", 1.0, 50000.0)
        equity = portfolio.mark_to_market({"BTCUSDT": 51000.0})
    """

    initial_cash: float = 100_000.0
    # None 表示未显式指定, 回退为 initial_cash; 显式传 0.0 时保留 0
    cash: float | None = None
    positions: dict[str, Position] = field(default_factory=dict)
    total_fills: int = 0
    total_orders: int = 0
    total_fees: float = 0.0

    def __post_init__(self) -> None:
        if self.cash is None:
            self.cash = self.initial_cash

    @property
    def total_realized_pnl(self) -> float:
        return sum(p.realized_pnl for p in self.positions.values())

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    def get_position(self, symbol: str) -> Position:
        """获取或创建持仓。"""
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def update_on_fill(self, symbol: str, side: str, quantity: float, price: float, fee: float = 0.0) -> None:
        """成交回写: 更新持仓、扣减手续费。"""
        pos = self.get_position(symbol)
        pos.update_on_fill(side, quantity, price)

        # 扣减手续费
        self.cash -= fee
        self.total_fees += fee
        self.total_fills += 1

        # 扣减/增加现金 (简化版: 实际应按成交额算)
        notional = quantity * price
        if side.lower() == "buy":
            self.cash -= notional
        else:
            self.cash += notional

    def mark_to_market(self, prices: dict[str, float]) -> float:
        """按当前价格字典估值所有持仓，返回总权益。"""
        total_unreal = 0.0
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, pos.avg_price)
            pos.mark_to_market(price)
            total_unreal += pos.unrealized_pnl
        return self.cash + sum(pos.quantity * prices.get(pos.symbol, pos.avg_price) for pos in self.positions.values())

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict (用于 WebSocket 推送)。"""
        return {
            "cash": round(self.cash, 4),
            "initial_cash": self.initial_cash,
            "total_realized_pnl": round(self.total_realized_pnl, 4),
            "total_unrealized_pnl": round(self.total_unrealized_pnl, 4),
            "total_fees": round(self.total_fees, 4),
            "total_fills": self.total_fills,
            "total_orders": self.total_orders,
            "positions": {
                sym: {
                    "quantity": round(p.quantity, 6),
                    "avg_price": round(p.avg_price, 2),
                    "side": p.side,
                    "realized_pnl": round(p.realized_pnl, 4),
                    "unrealized_pnl": round(p.unrealized_pnl, 4),
                }
                for sym, p in self.positions.items()
                if p.quantity != 0
            },
        }
