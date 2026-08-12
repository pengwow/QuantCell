"""InteractionAgent — QuantCell's upper-layer AI interaction agent.

Handles NLU, intent routing, tool orchestration, and response formatting.
Delegates trading decisions to DecisionAgent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentCategory(str, Enum):
    """User intent categories."""
    TRADING_DECISION = "trading_decision"
    BACKTEST = "backtest"
    RL_TRAINING = "rl_training"
    STRATEGY_GENERATION = "strategy_generation"
    DATA_QUERY = "data_query"
    RISK_ASSESSMENT = "risk_assessment"
    GENERAL = "general"


@dataclass
class Intent:
    """Parsed user intent."""
    category: IntentCategory
    raw_message: str
    resolved_prompt: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Agent response."""
    content: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# Keywords for intent classification
_INTENT_KEYWORDS: dict[IntentCategory, list[str]] = {
    IntentCategory.BACKTEST: ["回测", "backtest", "测试策略", "历史回测"],
    IntentCategory.RL_TRAINING: ["训练", "train", "强化学习", "rl", "ppo", "sac", "dqn"],
    IntentCategory.TRADING_DECISION: ["买入", "卖出", "buy", "sell", "下单", "交易", "持仓"],
    IntentCategory.STRATEGY_GENERATION: ["生成策略", "写策略", "创建策略", "策略代码"],
    IntentCategory.DATA_QUERY: ["数据", "行情", "k线", "价格", "走势"],
    IntentCategory.RISK_ASSESSMENT: ["风险", "风控", "回撤", "止损"],
}


def _classify_intent(message: str) -> IntentCategory:
    """Classify user intent based on keywords."""
    message_lower = message.lower()
    for category, keywords in _INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in message_lower:
                return category
    return IntentCategory.GENERAL


class InteractionAgent:
    """QuantCell's interaction-layer agent.

    Handles NLU, intent routing, tool orchestration, and response formatting.
    Delegates trading decisions to DecisionAgent.

    Args:
        llm_provider: LLM provider for NLU and response generation.
        services: Service registry for tool execution.
        decision_agent: Optional DecisionAgent for trading decisions.
    """

    def __init__(
        self,
        llm_provider: Any | None = None,
        services: dict[str, Any] | None = None,
        decision_agent: Any | None = None,
    ):
        self.llm = llm_provider
        self.services = services or {}
        self._decision_agent = decision_agent

    def _parse_intent_static(self, message: str) -> Intent:
        """Parse user intent using keyword matching (static, no LLM)."""
        category = _classify_intent(message)
        return Intent(
            category=category,
            raw_message=message,
            resolved_prompt=message,
        )

    async def process(self, message: str, session: Any | None = None) -> AgentResponse:
        """Process user message.

        Args:
            message: User message.
            session: Optional session context.

        Returns:
            AgentResponse with content and actions.
        """
        intent = self._parse_intent_static(message)

        if intent.category == IntentCategory.TRADING_DECISION:
            return await self._delegate_to_decision(intent)
        elif intent.category == IntentCategory.BACKTEST:
            return await self._handle_backtest(intent)
        elif intent.category == IntentCategory.RL_TRAINING:
            return await self._handle_rl(intent)
        elif intent.category == IntentCategory.STRATEGY_GENERATION:
            return await self._handle_strategy_gen(intent)
        else:
            return await self._handle_general(message)

    async def _delegate_to_decision(self, intent: Intent) -> AgentResponse:
        """Delegate trading decision to DecisionAgent."""
        if self._decision_agent is None:
            return AgentResponse(
                content="交易决策Agent未配置。请先初始化DecisionAgent。",
            )
        return await self._decision_agent.execute(intent)

    async def _handle_backtest(self, intent: Intent) -> AgentResponse:
        """Handle backtest-related requests."""
        return AgentResponse(
            content=f"收到回测请求: {intent.raw_message}",
            actions=[{"type": "backtest", "params": intent.parameters}],
        )

    async def _handle_rl(self, intent: Intent) -> AgentResponse:
        """Handle RL training requests."""
        return AgentResponse(
            content=f"收到RL训练请求: {intent.raw_message}",
            actions=[{"type": "rl_train", "params": intent.parameters}],
        )

    async def _handle_strategy_gen(self, intent: Intent) -> AgentResponse:
        """Handle strategy generation requests."""
        return AgentResponse(
            content=f"收到策略生成请求: {intent.raw_message}",
            actions=[{"type": "strategy_gen", "params": intent.parameters}],
        )

    async def _handle_general(self, message: str) -> AgentResponse:
        """Handle general conversation."""
        return AgentResponse(
            content=f"收到消息: {message}",
        )
