"""Agent Traders 测试"""

from unittest.mock import MagicMock

from strategy.agent_traders import (
    EnsembleTrader,
    ReActTrader,
    StrategyTrader,
    TraderRegistry,
)


class MockAction:
    """模拟 Action 对象"""

    def __init__(self, action_type="Hold", confidence=0.5, target_position=0.0):
        self.action_type = action_type
        self.confidence = confidence
        self.target_position = target_position


class MockStrategy:
    """模拟 BaseStrategy"""

    def __init__(self, name="MockStrategy", action="hold", confidence=0.5):
        self.__class__.__name__ = name
        self._action = action
        self._confidence = confidence

    def on_start(self, ctx=None):
        pass

    def on_bar(self, bar, ctx=None):
        return MockAction(self._action, self._confidence, 0.1 if self._action != "hold" else 0.0)

    def on_stop(self, ctx=None):
        pass


class TestStrategyTrader:
    """StrategyTrader 测试"""

    def test_decide_buy(self):
        """buy 策略正确转换"""
        strategy = MockStrategy(action="buy", confidence=0.8)
        trader = StrategyTrader(strategy, id="test_buy")
        bar = {"open": 50000, "high": 51000, "low": 49000, "close": 50500, "volume": 100}
        result = trader.decide(bar)
        assert result["action"] == "buy"
        assert result["confidence"] == 0.8
        assert result["target_position"] == 0.1

    def test_decide_sell(self):
        """sell 策略正确转换"""
        strategy = MockStrategy(action="sell", confidence=0.6)
        trader = StrategyTrader(strategy, id="test_sell")
        bar = {"open": 50000, "high": 51000, "low": 49000, "close": 49500, "volume": 200}
        result = trader.decide(bar)
        assert result["action"] == "sell"
        assert result["confidence"] == 0.6

    def test_decide_hold(self):
        """hold 策略正确转换"""
        strategy = MockStrategy(action="hold", confidence=0.5)
        trader = StrategyTrader(strategy, id="test_hold")
        bar = {"open": 50000, "high": 51000, "low": 49000, "close": 50000, "volume": 50}
        result = trader.decide(bar)
        assert result["action"] == "hold"

    def test_decide_error_returns_hold(self):
        """异常时返回 hold"""
        strategy = MagicMock()
        strategy.__class__.__name__ = "BrokenStrategy"
        strategy.on_bar.side_effect = Exception("API Error")
        trader = StrategyTrader(strategy, id="test_error")
        bar = {"open": 50000, "close": 50500}
        result = trader.decide(bar)
        assert result["action"] == "hold"
        assert result["confidence"] == 0.0

    def test_trader_id(self):
        """trader ID 正确设置"""
        strategy = MockStrategy(name="CustomName")
        trader = StrategyTrader(strategy, id="my_id")
        assert trader.id == "my_id"

    def test_default_id_from_strategy(self):
        """默认 ID 从策略类名生成"""
        strategy = MockStrategy(name="DualEMACrossover")
        trader = StrategyTrader(strategy)
        assert "dualemacrossover" in trader.id

    def test_position_scale_applied(self):
        """target_position 使用 position_scale"""
        strategy = MockStrategy(action="buy", confidence=0.5)
        trader = StrategyTrader(strategy, position_scale=0.2)
        bar = {"open": 50000, "close": 50500}
        result = trader.decide(bar)
        # target_position = confidence * position_scale = 0.5 * 0.2 = 0.1
        assert result["target_position"] == 0.1


class TestReActTrader:
    """ReActTrader 测试"""

    def test_no_agent_returns_hold(self):
        """无 agent 时返回 hold"""
        trader = ReActTrader(id="no_agent")
        bar = {"open": 50000, "close": 50500}
        result = trader.decide(bar)
        assert result["action"] == "hold"
        assert result["confidence"] == 0.0

    def test_with_mock_agent(self):
        """有 agent 时正常决策"""
        mock_agent = MagicMock()
        mock_agent.run_step.return_value = {
            "thought": "Market looks bullish",
            "action": {"tool": "place_order", "args": {"side": "buy", "target_position": 0.1}},
            "observation": {"status": "ok"},
        }
        trader = ReActTrader(react_agent=mock_agent, id="llm_test")
        bar = {"open": 50000, "close": 50500, "high": 51000, "low": 49000, "volume": 100}
        result = trader.decide(bar)
        assert result["action"] == "buy"
        assert result["confidence"] > 0.5
        assert "Market data" in mock_agent.run_step.call_args[0][1]


class TestTraderRegistry:
    """TraderRegistry 测试"""

    def test_register_and_get(self):
        """注册和获取 trader"""
        registry = TraderRegistry()
        trader = StrategyTrader(MockStrategy(), id="t1")
        registry.register(trader)
        assert len(registry) == 1
        all_traders = registry.get_all()
        assert len(all_traders) == 1
        assert all_traders[0].id == "t1"

    def test_unregister(self):
        """注销 trader"""
        registry = TraderRegistry()
        trader = StrategyTrader(MockStrategy(), id="t1")
        registry.register(trader)
        assert len(registry) == 1
        result = registry.unregister("t1")
        assert result is True
        assert len(registry) == 0

    def test_unregister_nonexistent(self):
        """注销不存在的 trader"""
        registry = TraderRegistry()
        result = registry.unregister("nonexistent")
        assert result is False

    def test_start_stop_all(self):
        """启动和停止所有 trader"""
        registry = TraderRegistry()
        trader = StrategyTrader(MockStrategy(), id="t1")
        registry.register(trader)
        # 不抛异常
        registry.start_all()
        registry.stop_all()


class TestEnsembleTrader:
    """EnsembleTrader 测试"""

    def test_no_ensemble_returns_hold(self):
        """无 ensemble 时返回 hold"""
        trader = EnsembleTrader(ensemble_manager=None)
        bar = {"open": 50000, "close": 50500}
        result = trader.decide(bar)
        assert result["action"] == "hold"

    def test_buy_prediction(self):
        """Buy 预测正确映射"""
        mock_ensemble = MagicMock()
        mock_ensemble.predict.return_value = {"Buy": 0.7, "Sell": 0.15, "Hold": 0.15}
        trader = EnsembleTrader(ensemble_manager=mock_ensemble)
        bar = {"open": 50000, "close": 50500}
        result = trader.decide(bar)
        assert result["action"] == "buy"
        assert result["confidence"] == 0.7

    def test_sell_prediction(self):
        """Sell 预测正确映射"""
        mock_ensemble = MagicMock()
        mock_ensemble.predict.return_value = {"Buy": 0.1, "Sell": 0.8, "Hold": 0.1}
        trader = EnsembleTrader(ensemble_manager=mock_ensemble)
        bar = {"open": 50000, "close": 49500}
        result = trader.decide(bar)
        assert result["action"] == "sell"
        assert result["confidence"] == 0.8
