"""ReActTrader 与真实 axon_quant ReActAgent 兼容性测试。

验证点:
1. ReActTrader 调用 agent.run_step(history, observation) 签名匹配
2. ReActTrader._history 数据格式符合 List[Dict[str, Any]] 要求
3. 返回结果 dict 格式解析正确
"""

from unittest.mock import MagicMock, patch

import pytest

from strategy.agent_traders import ReActTrader


class TestReActAgentCompatibility:
    """验证 ReActTrader 与 axon_quant ReActAgent 的接口兼容性。"""

    def test_run_step_signature_matches_old_agent(self):
        """ReActTrader 调用 agent.run_step(history: List[Dict], observation: str) 签名匹配旧版 ReActAgent。"""
        # axon_quant.agent.ReActAgent.run_step 签名: (history: List[Dict[str, Any]], observation: str) -> Dict[str, Any]
        mock_agent = MagicMock()
        mock_agent.run_step.return_value = {
            "thought": "市场突破",
            "action": {"tool": "buy", "args": {"target_position": 0.2}},
        }

        trader = ReActTrader(react_agent=mock_agent, id="compat_test")
        bar = {"open": 100, "high": 105, "low": 98, "close": 103, "volume": 1000, "symbol": "BTCUSDT"}

        result = trader.decide(bar)

        # 验证 run_step 被正确调用
        assert mock_agent.run_step.called
        call_args = mock_agent.run_step.call_args[0]
        # 第一个参数是 _history (list[dict])
        assert isinstance(call_args[0], list)
        assert len(call_args[0]) == 0  # 第一次调用 history 应为空
        # 第二个参数是 observation (str)
        assert isinstance(call_args[1], str)
        assert "Market data" in call_args[1]  # 包含 bar 数据

        # 验证返回值格式正确
        assert result["action"] == "buy"
        assert result["target_position"] == 0.2
        assert result["confidence"] > 0

    def test_history_format_is_list_of_dicts(self):
        """_history 必须是 List[Dict[str, Any]] 格式 (供 run_step 使用)。"""
        mock_agent = MagicMock()
        mock_agent.run_step.side_effect = [
            {"thought": "第一根", "action": {"tool": "buy", "args": {}}},
            {"thought": "第二根", "action": {"tool": "hold", "args": {}}},
        ]

        trader = ReActTrader(react_agent=mock_agent, id="history_test")
        bar = {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "symbol": "BTCUSDT"}

        trader.decide(bar)
        trader.decide(bar)

        assert len(trader._history) == 2
        for entry in trader._history:
            assert isinstance(entry, dict)
            assert "observation" in entry
            assert "result" in entry
            assert isinstance(entry["observation"], str)
            assert isinstance(entry["result"], dict)

    def test_new_agent_constructs_with_llm_provider(self):
        """ReActTrader.__init__ 在无预配置 agent 时, 应能用 llm_provider 构造新 agent。"""
        mock_llm = MagicMock()
        # patch axon_quant.llm.ReActAgent 以避免真实 LLM 初始化
        with patch("axon_quant.llm.ReActAgent") as mock_react_class:
            mock_react_instance = MagicMock()
            mock_react_instance.run_step.return_value = {"thought": "ok", "action": {"tool": "sell", "args": {}}}
            mock_react_class.return_value = mock_react_instance

            trader = ReActTrader(
                react_agent=None,
                id="construct_test",
                llm_provider=mock_llm,
                tools=[],
            )
            assert trader._agent is not None
            mock_react_class.assert_called_once()

            bar = {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "symbol": "BTCUSDT"}
            result = trader.decide(bar)
            assert result["action"] == "sell"

    def test_fallback_to_hold_when_no_agent(self):
        """无 agent 实例也无 llm_provider 时, 应返回 hold。"""
        trader = ReActTrader(react_agent=None, id="no_agent")
        bar = {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "symbol": "BTCUSDT"}
        result = trader.decide(bar)
        assert result["action"] == "hold"
        assert result["confidence"] == 0.0

    def test_history_not_duplicated_in_swarm(self):
        """两次相同 bar 调用, run_step 应收到递增的 history (非重复)。"""
        call_histories = []

        def capture_run_step(history, obs):
            call_histories.append(list(history))
            return {"thought": f"iter_{len(call_histories)}", "action": {"tool": "hold", "args": {}}}

        mock_agent = MagicMock()
        mock_agent.run_step.side_effect = capture_run_step

        trader = ReActTrader(react_agent=mock_agent, id="dedup_test")
        bar = {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "symbol": "BTCUSDT"}

        trader.decide(bar)
        trader.decide(bar)
        trader.decide(bar)

        # 每次 run_step 收到的 history 长度应递增
        assert len(call_histories[0]) == 0
        assert len(call_histories[1]) == 1
        assert len(call_histories[2]) == 2
        # history 内容不应相同
        assert call_histories[0] != call_histories[1]
        assert call_histories[1] != call_histories[2]


class TestSwarmRunnerWithReActTrader:
    """SwarmRunner + ReActTrader 集成测试。"""

    def test_swarm_with_react_trader_produces_vote(self):
        """ReActTrader 加入 SwarmRunner 后, on_bar 应产出包含该 trader vote 的决策。"""
        from axon_bridge import SwarmRunner

        mock_agent = MagicMock()
        mock_agent.run_step.return_value = {
            "thought": "看涨",
            "action": {"tool": "buy", "args": {"target_position": 0.3}},
        }

        trader = ReActTrader(react_agent=mock_agent, id="llm_voter")
        swarm = SwarmRunner(traders=[trader])

        decision = swarm.on_bar(
            {
                "open": 50000,
                "high": 51000,
                "low": 49000,
                "close": 50500,
                "volume": 100,
                "symbol": "BTCUSDT",
            }
        )

        assert decision["final_action"] == "Buy"
        votes = decision["votes"]
        assert len(votes) == 1
        assert votes[0]["agent_id"] == "llm_voter"
        assert votes[0]["action"] == "Buy"
        assert votes[0]["confidence"] > 0.5

    def test_swarm_with_multiple_react_traders(self):
        """多个 ReActTrader 加入 Swarm, 应产出多 voter。"""
        from axon_bridge import SwarmRunner

        def make_agent(action="buy"):
            agent = MagicMock()
            agent.run_step.return_value = {
                "thought": f"决策 {action}",
                "action": {"tool": action, "args": {"target_position": 0.1}},
            }
            return agent

        t1 = ReActTrader(react_agent=make_agent("buy"), id="trader_1")
        t2 = ReActTrader(react_agent=make_agent("buy"), id="trader_2")

        swarm = SwarmRunner(traders=[t1, t2])
        decision = swarm.on_bar(
            {
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 103,
                "volume": 1000,
                "symbol": "TEST",
            }
        )

        assert len(decision["votes"]) == 2
        for v in decision["votes"]:
            assert v["action"] == "Buy"
            assert v["agent_id"].startswith("trader_")
