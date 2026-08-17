"""Tests for agent/core/interaction_agent.py — InteractionAgent."""

import pytest


def test_interaction_agent_creation():
    """InteractionAgent可以被创建"""
    from agent.core.interaction_agent import InteractionAgent
    agent = InteractionAgent(llm_provider=None, services={})
    assert agent is not None


def test_interaction_agent_parses_backtest_intent():
    """InteractionAgent能解析回测意图"""
    from agent.core.interaction_agent import InteractionAgent, IntentCategory
    agent = InteractionAgent(llm_provider=None, services={})
    intent = agent._parse_intent_static("帮我回测MACD策略")
    assert intent.category == IntentCategory.BACKTEST


def test_interaction_agent_parses_rl_intent():
    """InteractionAgent能解析RL训练意图"""
    from agent.core.interaction_agent import InteractionAgent, IntentCategory
    agent = InteractionAgent(llm_provider=None, services={})
    intent = agent._parse_intent_static("用PPO训练一个BTC策略")
    assert intent.category == IntentCategory.RL_TRAINING


def test_interaction_agent_parses_trading_intent():
    """InteractionAgent能解析交易意图"""
    from agent.core.interaction_agent import InteractionAgent, IntentCategory
    agent = InteractionAgent(llm_provider=None, services={})
    intent = agent._parse_intent_static("买入0.1个BTC")
    assert intent.category == IntentCategory.TRADING_DECISION


def test_interaction_agent_parses_general_intent():
    """InteractionAgent能解析通用意图"""
    from agent.core.interaction_agent import InteractionAgent, IntentCategory
    agent = InteractionAgent(llm_provider=None, services={})
    intent = agent._parse_intent_static("今天天气怎么样")
    assert intent.category == IntentCategory.GENERAL


@pytest.mark.asyncio
async def test_interaction_agent_process_general():
    """InteractionAgent处理通用消息"""
    from agent.core.interaction_agent import InteractionAgent
    agent = InteractionAgent(llm_provider=None, services={})
    response = await agent.process("你好")
    assert response.content is not None


@pytest.mark.asyncio
async def test_interaction_agent_process_backtest():
    """InteractionAgent处理回测请求"""
    from agent.core.interaction_agent import InteractionAgent
    agent = InteractionAgent(llm_provider=None, services={})
    response = await agent.process("帮我回测MACD策略")
    assert "回测" in response.content


@pytest.mark.asyncio
async def test_interaction_agent_delegates_to_decision():
    """InteractionAgent将交易决策委托给DecisionAgent"""
    from agent.core.interaction_agent import InteractionAgent

    class MockDecisionAgent:
        async def execute(self, intent):
            from agent.core.interaction_agent import AgentResponse
            return AgentResponse(content="交易决策已执行")

    agent = InteractionAgent(
        llm_provider=None,
        services={},
        decision_agent=MockDecisionAgent(),
    )
    response = await agent.process("买入0.1个BTC")
    assert "交易决策已执行" in response.content
