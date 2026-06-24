"""DecisionAgent — axon_quant-driven trading decision agent.

Uses axon_quant's trading tools for ReAct-style trading decisions.
"""

from __future__ import annotations

from typing import Any

from axon_quant.trading import (
    PlaceOrderTool,
    QueryPortfolioTool,
    CancelOrderTool,
    MockTradingBackend,
    RiskLimits,
)

from agent.core.interaction_agent import AgentResponse, Intent


class DecisionAgent:
    """axon_quant-driven trading decision agent.

    Args:
        services: Service registry.
    """

    def __init__(self, services: dict[str, Any] | None = None):
        self.services = services or {}
        self._backend = MockTradingBackend()
        risk_limits = RiskLimits()
        self._tools = {
            "place_order": PlaceOrderTool(self._backend, "dry_run", risk_limits),
            "query_portfolio": QueryPortfolioTool(self._backend),
            "cancel_order": CancelOrderTool(self._backend, risk_limits),
        }

    def get_tool_names(self) -> list[str]:
        """Get list of available tool names."""
        return list(self._tools.keys())

    async def execute(self, intent: Intent) -> AgentResponse:
        """Execute trading decision.

        Args:
            intent: Parsed user intent.

        Returns:
            AgentResponse with trading result.
        """
        return AgentResponse(
            content=f"交易决策Agent收到请求: {intent.raw_message}",
            actions=[{"type": "trading_decision", "status": "pending"}],
            metadata={"tools_available": self.get_tool_names()},
        )
