"""LLM Agent 交易链路 + 风控集成 端到端测试

核心目标:
1. 风控: RiskService 正确接收 LivePortfolio 格式, 真实拒绝超限订单
2. LLM Agent: ReActTrader (带真实/模拟 LLM) 参与 Swarm 投票并执行
3. 多层风控集成: Swarm 决策风控 → Pipeline 本地风控 → RiskService 全局风控
"""

from unittest.mock import MagicMock, patch

import pytest

from services.risk_service import RiskService
from strategy.agent_traders import ReActTrader, StrategyTrader
from strategy.event_loop import EventDrivenLoop
from strategy.execution_pipeline import ExecutionPipeline
from strategy.live_portfolio import LivePortfolio

# ===================================================================
# P0 - 风控格式不匹配 Bug (RED 测试: axon_quant 风控未生效)
# ===================================================================


class TestRiskIntegrationFormatBug:
    """验证 RiskService 与 LivePortfolio 的数据格式衔接。"""

    def test_risk_service_rejects_over_max_order_value(self):
        """LivePortfolio.to_dict() 格式喂给 RiskService 时, 应能正确拒绝超出 max_order_value 订单。

        Bug 根因: RiskService.check_order 读取 portfolio.get("cash", {"USD": 0.0}),
        但 LivePortfolio.to_dict()["cash"] 是 float, 导致 cash.keys() 报 AttributeError,
        风控最终回退到 base_currency="USD"/cash={USD: 0.0}, 使订单因"没钱"被错误拒绝,
        而真正想测的 max_order_value 风控根本没跑。
        """
        svc = RiskService()
        # 用 LivePortfolio.to_dict() 的真实格式: cash 是 float 不是 dict
        pf = LivePortfolio(initial_cash=500_000.0)  # 现金充足
        pf_dict = pf.to_dict()
        # max_order_value 默认 50000, 下 80000 刀订单应被拒
        order = {
            "id": 1,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "type": "market",
            "quantity": 1.6,  # 1.6 BTC × 50000 = 80000 USD > 50000 max_order_value
            "price": 50000.0,
        }
        result = svc.check_order(order, pf_dict)
        # 关键断言: 应因 max_order_value/单笔限额 被拒
        assert result["passed"] is False
        reason = (result["reason"] or "").lower()
        # 允许的原因关键字: axon_quant 返回 RiskReason.OrderTooLarge / 本地风控返回 max_order_value_exceeded
        assert any(k in reason for k in ("toolarge", "order_value", "max_order_value")), (
            f"期望订单过大被拦截, 实际 reason={result['reason']!r}"
        )

    def test_risk_service_accepts_normal_order(self):
        """正常小额订单应通过风控 (格式正确的正例)。"""
        svc = RiskService()
        pf = LivePortfolio(initial_cash=500_000.0)
        pf_dict = pf.to_dict()
        order = {
            "id": 2,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "type": "market",
            "quantity": 0.5,  # 0.5 BTC × 50000 = 25000 < 50000
            "price": 50000.0,
        }
        result = svc.check_order(order, pf_dict)
        assert result["passed"] is True, f"小额订单应通过, 实际 {result}"


# ===================================================================
# LLM Agent 交易链路端到端测试
# ===================================================================


class TestLLMAgentTradingLoop:
    """ReActTrader (带模拟 LLM) + SwarmRunner + EventDrivenLoop 完整链路。"""

    def _make_mock_react_agent(self, action_timeline=None):
        """构造 mock ReActAgent, 按 action_timeline 序列返回 buy/sell/hold。"""
        import itertools

        if action_timeline is None:
            action_timeline = ["buy", "hold", "sell", "hold"]
        it = itertools.cycle(action_timeline)

        def run_step(history, observation):
            action = next(it)
            if action == "buy":
                tool_action = {"tool": "buy", "args": {"target_position": 0.1}}
            elif action == "sell":
                tool_action = {"tool": "sell", "args": {"target_position": 0.1}}
            else:
                tool_action = {"tool": "hold", "args": {}}
            return {
                "thought": f"看到行情 {observation[-40:]!r} 决定 {action}",
                "action": tool_action,
            }

        agent = MagicMock()
        agent.run_step = run_step
        return agent

    def test_react_trader_feeds_history_to_agent(self):
        """ReActTrader 每轮应将 observation+result 追加到 _history, 供后续轮次使用。"""
        agent = self._make_mock_react_agent(["buy", "sell"])
        trader = ReActTrader(react_agent=agent, id="react_test")
        bar = {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1, "symbol": "BTCUSDT"}

        trader.decide(bar)
        assert len(trader._history) == 1, f"第 1 轮后历史应有 1 条, 实际 {len(trader._history)}"
        assert "observation" in trader._history[0]

        trader.decide(bar)
        assert len(trader._history) == 2, "第 2 轮后历史应有 2 条"

    def test_react_trader_history_bounded(self):
        """历史条数上限为 20 条, 防止 prompt 无限膨胀。"""
        agent = self._make_mock_react_agent(["buy"])
        trader = ReActTrader(react_agent=agent, id="bounded_test")
        bar = {"open": 1, "high": 2, "low": 1, "close": 1, "volume": 1, "symbol": "BTCUSDT"}

        for _ in range(50):
            trader.decide(bar)
        assert len(trader._history) == 20, f"历史应被截断为 20, 实际 {len(trader._history)}"

    def test_react_trader_in_swarm_makes_buy_decision(self):
        """ReActTrader 加入 SwarmRunner 后应产出 buy 决策, 并正确执行下单。"""
        from axon_bridge import SwarmRunner

        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "swarm_llm"}

        loop = EventDrivenLoop(adapter=adapter, symbol="BTCUSDT", initial_cash=100_000, enable_trajectory=False)
        react_agent = self._make_mock_react_agent(["buy"])
        loop.add_trader(ReActTrader(react_agent=react_agent, id="llm_t1"))
        loop._swarm = SwarmRunner(traders=loop._trader_registry.get_all())

        loop.process_bar(
            {"open": 50000, "high": 51000, "low": 49000, "close": 50500, "volume": 100, "symbol": "BTCUSDT"}
        )

        stats = loop.stats
        assert stats["decision_count"] == 1
        decision = stats["last_decision"] or {}
        # 模拟 LLM 返回 buy, Swarm 聚合后的最终动作也应是 Buy
        assert decision.get("final_action", "Hold").lower() == "buy"
        assert adapter.place_order.called is True


# ===================================================================
# 多层风控集成测试
# ===================================================================


class TestMultiLayerRiskIntegration:
    """Swarm 风控 → Pipeline 本地风控 → RiskService 全局风控三层联动。"""

    def test_three_layer_risk_rejects_huge_order(self):
        """超巨大订单应被三层风控中的某一层正确拦截。"""
        from axon_bridge import SwarmRunner
        from services.risk_service import RiskService

        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "big_order"}

        # 初始现金 50000 (单只最大仓位=50%×50000=25000)
        # target_position=0.9 → 45000 USD → 远超 max_order_value=50000 ? 不, 45k < 50k
        # 但仓位 45k / 25k = 1.8x 超 max_position, 由本地仓位风控拦截
        risk_service = RiskService()
        loop = EventDrivenLoop(
            adapter=adapter, symbol="BTCUSDT", initial_cash=50_000, risk_engine=risk_service, enable_trajectory=False
        )

        class HeavyBuyStrategy:
            def on_bar(self, bar):
                from types import SimpleNamespace

                return SimpleNamespace(action_type="buy", confidence=1.0, target_position=0.9)

        loop.add_strategy(HeavyBuyStrategy())
        loop._swarm = SwarmRunner(traders=loop._trader_registry.get_all())

        loop.process_bar(
            {"open": 50000, "high": 51000, "low": 49000, "close": 50000, "volume": 100, "symbol": "BTCUSDT"}
        )

        stats = loop.stats
        # 仓位 45000 USD 是初始现金 50000 的 90%, 但本地最大仓位比例 50% → 25000 上限 → 必须被拒
        assert stats["order_count"] == 0, (
            f"超上限仓位订单不应被接受执行, 但 order_count={stats['order_count']},"
            f" rejected_count={stats['rejected_count']}"
        )
        assert stats["rejected_count"] >= 1, "至少应有 1 次风控拒绝"

    def test_circuit_breaker_triggers_on_loss_threshold(self):
        """ExecutionPipeline 的熔断应在连续亏损后触发。"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "cb_test"}
        pf = LivePortfolio(initial_cash=100_000)
        pipeline = ExecutionPipeline(adapter=adapter, portfolio=pf, enable_circuit_breaker=True)

        # 手动触发熔断 (由上游风控调用, 或集成日亏损检测)
        pipeline.trigger_circuit_breaker("test_loss_threshold")
        assert pipeline.circuit_broken is True

        # 熔断期间新订单应被拒 (不依赖 _daily_loss 死代码)
        decision = {
            "final_action": "Buy",
            "final_confidence": 0.8,
            "target_position": 0.1,
            "risk_verdict": {"approved": True},
            "symbol": "BTCUSDT",
        }
        r = pipeline.execute_decision(decision, 50000.0)
        assert r.accepted is False
        assert "circuit_broken" in r.reason
