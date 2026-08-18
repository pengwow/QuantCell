"""RiskService — axon_bridge.risk 业务封装。

QuantCell 业务代码统一从 ``axon_bridge`` 入口拿 axon_quant 能力,
不在 services 层直接 import 第三方包。
"""

from __future__ import annotations

from typing import Any

try:
    # 走适配层,不直接 import axon_quant
    from axon_bridge import (
        DefaultRiskEngine,
        RiskConfig,
        make_order,
        make_portfolio,
    )

    AVAILABLE = True
except ImportError:
    AVAILABLE = False


class RiskService:
    """Risk service wrapping axon_quant.risk.DefaultRiskEngine (via axon_bridge)."""

    def __init__(self, config: dict[str, Any] | None = None):
        if not AVAILABLE:
            msg = "axon_quant.risk not available"
            raise RuntimeError(msg)
        risk_config = RiskConfig(**(config or {}))
        self._engine = DefaultRiskEngine(risk_config)

    def check_order(
        self,
        order: dict[str, Any],
        portfolio: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if order passes risk controls."""
        axon_order = make_order(
            id=order.get("id", 0),
            symbol=order.get("symbol", "BTC-USDT"),
            side=order.get("side", "Buy"),
            type=order.get("type", "limit"),
            quantity=order.get("quantity", 0.0),
            price=order.get("price", 0.0),
        )
        cash = portfolio.get("cash", {"USD": 0.0})
        base_currency = next(iter(cash.keys())) if cash else "USD"
        axon_portfolio = make_portfolio(
            base_currency=base_currency,
            cash=cash,
        )

        result = self._engine.check_order(axon_order, axon_portfolio)
        return {
            "passed": result.is_allow,
            "reason": str(result.reason) if result.reason else None,
        }

    def get_metrics(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get current risk metrics."""
        cash = (portfolio or {}).get("cash", {"USD": 0.0})
        base_currency = next(iter(cash.keys())) if cash else "USD"
        axon_portfolio = make_portfolio(base_currency=base_currency, cash=cash)
        return self._engine.metrics(axon_portfolio)

    def reset_daily(self) -> None:
        """Reset daily counters."""
        self._engine.reset_daily()
