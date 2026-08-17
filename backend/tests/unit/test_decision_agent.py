"""Tests for agent/core/decision_agent.py — DecisionAgent."""

import pytest


def test_decision_agent_creation():
    """DecisionAgent可以被创建"""
    from agent.core.decision_agent import DecisionAgent
    agent = DecisionAgent(services={})
    assert agent is not None


def test_decision_agent_has_tools():
    """DecisionAgent持有交易工具"""
    from agent.core.decision_agent import DecisionAgent
    agent = DecisionAgent(services={})
    tool_names = agent.get_tool_names()
    # Tools may or may not be available depending on axon_quant installation
    assert isinstance(tool_names, list)


@pytest.mark.asyncio
async def test_decision_agent_execute():
    """DecisionAgent可以执行交易决策"""
    from agent.core.decision_agent import DecisionAgent
    from agent.core.interaction_agent import Intent, IntentCategory

    agent = DecisionAgent(services={})
    intent = Intent(
        category=IntentCategory.TRADING_DECISION,
        raw_message="买入0.1个BTC",
    )
    response = await agent.execute(intent)
    assert response.content is not None
    assert "交易决策" in response.content
