"""SwarmOrchestrator 装配与行为测试。

验证多智能体编排器的完整装配链路:
  规则策略 + LLM Agent → SwarmOrchestrator → EventDrivenLoop → SwarmRunner → Pipeline → Execution
"""

from unittest.mock import MagicMock

import pytest

from strategy.swarm_orchestrator import (
    LLMAgentSpec,
    OrchestratorConfig,
    StrategySpec,
    SwarmOrchestrator,
)


class TestSwarmOrchestrator:
    """SwarmOrchestrator 装配与行为测试。"""

    def test_build_with_strategies_only(self):
        """只注册规则策略, build() 应返回可 process_bar 的 loop。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "rule_only"}

        class SimpleStrategy:
            def on_bar(self, bar):
                from types import SimpleNamespace

                return SimpleNamespace(action_type="buy", confidence=0.9, target_position=0.2)

        orch = SwarmOrchestrator(adapter=adapter, symbol="BTCUSDT", initial_cash=100_000, enable_trajectory=False)
        orch.add_strategy(SimpleStrategy())
        loop = orch.build()

        assert loop is not None
        # 手动触发 bar, 验证完整链路可执行
        loop.process_bar(
            {
                "open": 50000,
                "high": 51000,
                "low": 49000,
                "close": 50000,
                "volume": 100,
                "symbol": "BTCUSDT",
            }
        )
        stats = loop.stats
        assert stats["decision_count"] == 1
        assert stats["order_count"] == 1
        assert stats["portfolio"]["positions"]["BTCUSDT"]["quantity"] > 0

    def test_build_with_llm_agent_only(self):
        """只注册 LLM Agent (ReActTrader), build() 后应产出 buy 决策。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "llm_only"}

        # Mock ReActAgent: 返回 buy 工具调用
        mock_agent = MagicMock()
        mock_agent.run_step.return_value = {
            "thought": "市场突破阻力位, 建议买入",
            "action": {"tool": "buy", "args": {"target_position": 0.3}},
        }

        orch = SwarmOrchestrator(adapter=adapter, symbol="BTCUSDT", initial_cash=100_000, enable_trajectory=False)
        orch.add_llm_agent(mock_agent, id="test_llm")
        loop = orch.build()

        loop.process_bar(
            {
                "open": 50000,
                "high": 51000,
                "low": 49000,
                "close": 50500,
                "volume": 100,
                "symbol": "BTCUSDT",
            }
        )
        stats = loop.stats
        assert stats["decision_count"] == 1
        assert stats["order_count"] == 1
        assert adapter.place_order.called

    def test_build_with_mixed_strategies_and_llm(self):
        """混合: 规则策略 + LLM Agent 同时注册, Swarm 聚合投票。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "mixed"}

        class TrendStrategy:
            def on_bar(self, bar):
                from types import SimpleNamespace

                return SimpleNamespace(action_type="buy", confidence=0.8, target_position=0.15)

        mock_llm = MagicMock()
        mock_llm.run_step.return_value = {
            "thought": "趋势向上",
            "action": {"tool": "buy", "args": {"target_position": 0.25}},
        }

        orch = SwarmOrchestrator(adapter=adapter, symbol="BTCUSDT", initial_cash=100_000, enable_trajectory=False)
        orch.add_strategy(TrendStrategy())
        orch.add_llm_agent(mock_llm, id="llm_trend")
        loop = orch.build()

        loop.process_bar(
            {
                "open": 50000,
                "high": 51000,
                "low": 49000,
                "close": 50500,
                "volume": 100,
                "symbol": "BTCUSDT",
            }
        )
        stats = loop.stats
        assert stats["decision_count"] == 1
        assert stats["order_count"] == 1
        # 验证 Swarm 聚合后的 target_position 已正确传递给 Pipeline
        decision = loop._last_decision
        assert decision is not None
        tp = float(decision.get("target_position", 0) or 0)
        # Swarm 聚合了两个 buy 决策, target_position 应该在 0.15~0.25 之间
        assert 0.05 < tp <= 0.35, f"聚合 target_position 异常: {tp}"

    def test_from_config_builds_same_as_manual(self):
        """from_config 构建的 loop 与手动添加再 build 的结果一致。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "cfg"}

        class S1:
            def on_bar(self, bar):
                from types import SimpleNamespace

                return SimpleNamespace(action_type="sell", confidence=0.7, target_position=0.1)

        mock_llm = MagicMock()
        mock_llm.run_step.return_value = {
            "thought": "回调",
            "action": {"tool": "sell", "args": {"target_position": 0.2}},
        }

        cfg = OrchestratorConfig(
            adapter=adapter,
            symbol="BTCUSDT",
            initial_cash=80_000,
            strategies=[StrategySpec(strategy=S1())],
            llm_agents=[LLMAgentSpec(react_agent=mock_llm, id="cfg_llm")],
            enable_trajectory=False,
        )
        orch = SwarmOrchestrator.from_config(cfg)
        loop = orch.build()

        loop.process_bar(
            {
                "open": 50000,
                "high": 51000,
                "low": 49000,
                "close": 49500,
                "volume": 100,
                "symbol": "BTCUSDT",
            }
        )
        stats = loop.stats
        assert stats["order_count"] == 1
        assert stats["portfolio"]["total_orders"] == 1

    def test_attach_risk_service_via_config(self):
        """通过 risk_config 绑定 RiskService, 超大订单应被拒。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "risky"}

        class BigOrder:
            def on_bar(self, bar):
                from types import SimpleNamespace

                return SimpleNamespace(action_type="buy", confidence=1.0, target_position=0.9)

        orch = SwarmOrchestrator(adapter=adapter, symbol="BTCUSDT", initial_cash=50_000, enable_trajectory=False)
        orch.add_strategy(BigOrder())
        orch.attach_risk_service(risk_config={"max_order_value": 30000})
        loop = orch.build()

        loop.process_bar(
            {
                "open": 50000,
                "high": 51000,
                "low": 49000,
                "close": 50000,
                "volume": 100,
                "symbol": "BTCUSDT",
            }
        )
        stats = loop.stats
        # 90% 仓位 = 45000 USD > max_order_value(30000), 应被拒
        # 或被 50% 仓位限制 (25000) 拦截
        assert stats["order_count"] == 0, f"超大订单应被拒, 实际 order_count={stats['order_count']}"
        assert stats["rejected_count"] >= 1


class TestCompositeAssembly:
    """M5 收编路径(assembly="composite")的装配开关测试。"""

    @staticmethod
    def _two_buy_strategies():
        from types import SimpleNamespace

        class BuyA:
            def on_bar(self, bar):
                return SimpleNamespace(action_type="buy", confidence=0.8, target_position=0.2)

        class BuyB:
            def on_bar(self, bar):
                return SimpleNamespace(action_type="buy", confidence=0.6, target_position=0.1)

        return BuyA(), BuyB()

    @staticmethod
    def _bar():
        return {
            "open": 50000,
            "high": 51000,
            "low": 49000,
            "close": 50000,
            "volume": 100,
            "symbol": "BTCUSDT",
        }

    def test_default_assembly_keeps_one_voter_per_strategy(self):
        """默认 assembly="loop": 每个规则策略各自注册为一个投票者。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "loop_mode"}
        orch = SwarmOrchestrator(adapter=adapter, symbol="BTCUSDT", initial_cash=100_000, enable_trajectory=False)
        for strategy in self._two_buy_strategies():
            orch.add_strategy(strategy)
        loop = orch.build()

        loop.process_bar(self._bar())

        assert loop.stats["order_count"] == 1
        assert len(loop._last_decision["votes"]) == 2

    def test_composite_assembly_registers_single_voter(self):
        """assembly="composite": 两个规则策略收编为一个 CompositeStrategy 投票者。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "composite_mode"}
        orch = SwarmOrchestrator(
            adapter=adapter,
            symbol="BTCUSDT",
            initial_cash=100_000,
            enable_trajectory=False,
            assembly="composite",
        )
        for strategy in self._two_buy_strategies():
            orch.add_strategy(strategy)
        loop = orch.build()

        loop.process_bar(self._bar())

        assert loop.stats["order_count"] == 1
        assert len(loop._last_decision["votes"]) == 1
        # 复合策略的 target_position 取子策略 confidence 加权均值:
        # (0.8*0.2 + 0.6*0.1) / (0.8 + 0.6) ≈ 0.157
        assert 0.05 < float(loop._last_decision["target_position"]) <= 0.2

    def test_unsupported_voting_with_composite_raises(self):
        """composite 模式不支持 unanimous, 构造期应给出明确错误。"""
        orch = SwarmOrchestrator(adapter=MagicMock(), enable_trajectory=False, voting="unanimous", assembly="composite")
        orch.add_strategy(self._two_buy_strategies()[0])
        with pytest.raises(ValueError):
            orch.build()

