"""RiskMonitor — Real-time risk monitoring for live trading.

Uses axon_quant's risk engine for pre-trade checks and alert tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from axon_quant.risk import DefaultRiskEngine, make_order, make_portfolio, make_risk_config


class RiskMonitor:
    """Real-time risk monitoring service.

    Args:
        config: Risk config dict with max_order_value, max_position, etc.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self.alerts: list[dict[str, Any]] = []
        risk_config = make_risk_config(**self._config)
        self._engine = DefaultRiskEngine(risk_config)

    def check_order(
        self,
        order: dict[str, Any],
        portfolio: dict[str, Any],
    ) -> bool:
        """Check if order passes risk controls.

        Args:
            order: Order dict with symbol, side, quantity, price.
            portfolio: Portfolio dict with cash.

        Returns:
            True if order passes, False otherwise.
        """
        axon_order = make_order(
            id=order.get("id", 0),
            symbol=order.get("symbol", "BTC-USDT"),
            side=order.get("side", "Buy"),
            type=order.get("type", "limit"),
            quantity=order.get("quantity", 0.0),
            price=order.get("price", 0.0),
        )
        cash = portfolio.get("cash", 0.0)
        base_currency = portfolio.get("base_currency", "USD")
        axon_portfolio = make_portfolio(base_currency=base_currency, cash={base_currency: cash})

        result = self._engine.check_order(axon_order, axon_portfolio)
        if not result.is_allow:
            self.alerts.append({
                "type": "order_rejected",
                "order": order,
                "reason": str(result.reason),
                "timestamp": datetime.now().isoformat(),
            })
        return result.is_allow

    def get_portfolio_risk(self, portfolio: dict[str, Any]) -> dict[str, Any]:
        """Get portfolio risk metrics."""
        return {
            "alerts_count": len(self.alerts),
            "recent_alerts": self.alerts[-5:] if self.alerts else [],
        }
