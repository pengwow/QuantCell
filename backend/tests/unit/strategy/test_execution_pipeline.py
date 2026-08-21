"""ExecutionPipeline 测试"""

from unittest.mock import MagicMock

from strategy.execution_pipeline import ExecutionPipeline, ExecutionResult
from strategy.live_portfolio import LivePortfolio


class TestExecutionPipeline:
    """ExecutionPipeline 测试"""

    def _make_pipeline(self, adapter=None, portfolio=None, risk_engine=None, callback=None):
        adapter = adapter or MagicMock()
        portfolio = portfolio or LivePortfolio(initial_cash=100_000)
        return ExecutionPipeline(
            adapter=adapter,
            portfolio=portfolio,
            risk_engine=risk_engine,
            event_callback=callback,
        )

    def test_hold_decision_no_execution(self):
        """Hold 决策不执行订单"""
        pipeline = self._make_pipeline()
        decision = {"final_action": "Hold", "final_confidence": 0.0}
        result = pipeline.execute_decision(decision, 50000.0)
        assert result.accepted is False
        assert result.reason == "hold"

    def test_qty_zero_no_execution(self):
        """数量为 0 不执行 (target_position 和 final_confidence 都为 0)"""
        pipeline = self._make_pipeline()
        decision = {
            "final_action": "Buy",
            "final_confidence": 0.0,
            "target_position": 0.0,
            "risk_verdict": {"approved": True},
            "symbol": "BTCUSDT",
        }
        result = pipeline.execute_decision(decision, 50000.0)
        assert result.accepted is False
        assert result.reason == "qty_zero"

    def test_missing_symbol_rejected(self):
        """决策缺少 symbol 时拒绝执行, 不静默交易默认品种"""
        pipeline = self._make_pipeline()
        decision = {
            "final_action": "Buy",
            "final_confidence": 0.8,
            "target_position": 0.1,
            "risk_verdict": {"approved": True},
        }
        result = pipeline.execute_decision(decision, 50000.0)
        assert result.accepted is False
        assert result.reason == "missing_symbol"

    def test_buy_decision_executes(self):
        """Buy 决策正常执行"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "test_123"}
        pipeline = self._make_pipeline(adapter=adapter)

        decision = {
            "final_action": "Buy",
            "final_confidence": 0.8,
            "target_position": 0.1,  # 10% of equity
            "risk_verdict": {"approved": True},
            "symbol": "BTCUSDT",
        }
        result = pipeline.execute_decision(decision, 50000.0)
        assert result.accepted is True
        assert result.side == "Buy"
        assert result.quantity > 0
        adapter.place_order.assert_called_once()

    def test_risk_rejected_not_executed(self):
        """风控拒绝不执行"""
        pipeline = self._make_pipeline()
        decision = {
            "final_action": "Buy",
            "final_confidence": 0.9,
            "target_position": 0.5,
            "risk_verdict": {"approved": False, "reason": "max_position_exceeded"},
        }
        result = pipeline.execute_decision(decision, 50000.0)
        assert result.accepted is False
        assert "max_position" in result.reason

    def test_local_risk_insufficient_cash(self):
        """现金不足被本地风控拦截"""
        adapter = MagicMock()
        portfolio = LivePortfolio(initial_cash=100_000)
        # 先全仓买入
        portfolio.update_on_fill("BTCUSDT", "buy", 1.99, 50000.0)
        pipeline = self._make_pipeline(adapter=adapter, portfolio=portfolio)

        decision = {
            "final_action": "Buy",
            "final_confidence": 0.9,
            "target_position": 0.5,
            "risk_verdict": {"approved": True},
            "symbol": "BTCUSDT",
        }
        result = pipeline.execute_decision(decision, 50000.0)
        # 现金不足应被拒绝
        assert result.accepted is False
        assert result.reason == "insufficient_cash"

    def test_circuit_breaker_blocks_trades(self):
        """熔断阻止交易"""
        pipeline = self._make_pipeline()
        pipeline.trigger_circuit_breaker("test")

        decision = {
            "final_action": "Buy",
            "final_confidence": 0.9,
            "target_position": 0.1,
            "risk_verdict": {"approved": True},
        }
        result = pipeline.execute_decision(decision, 50000.0)
        assert result.accepted is False
        assert "circuit_broken" in result.reason

    def test_event_callback_emits(self):
        """事件回调被触发"""
        events = []
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "cb_test"}
        pipeline = self._make_pipeline(adapter=adapter, callback=lambda t, d: events.append((t, d)))

        decision = {
            "final_action": "Buy",
            "final_confidence": 0.8,
            "target_position": 0.1,
            "risk_verdict": {"approved": True},
            "symbol": "BTCUSDT",
        }
        pipeline.execute_decision(decision, 50000.0)

        event_types = [e[0] for e in events]
        assert "order.placed" in event_types
        assert "order.filled" in event_types

    def test_portfolio_updated_on_fill(self):
        """成交后持仓更新"""
        adapter = MagicMock()
        adapter.place_order.return_value = {"order_id": "pf_test"}
        portfolio = LivePortfolio(initial_cash=100_000)
        pipeline = self._make_pipeline(adapter=adapter, portfolio=portfolio)

        decision = {
            "final_action": "Buy",
            "final_confidence": 0.8,
            "target_position": 0.1,
            "risk_verdict": {"approved": True},
            "symbol": "BTCUSDT",
        }
        pipeline.execute_decision(decision, 50000.0)

        assert portfolio.total_fills == 1
        pos = portfolio.get_position("BTCUSDT")
        assert pos.quantity > 0

    def test_qty_calc_respects_min_order(self):
        """最小下单量检查"""
        pipeline = self._make_pipeline()
        # 极小 ratio 应导致 qty 为 0
        pipeline._portfolio.cash = 1.0  # 几乎无现金
        qty = pipeline._calc_qty(0.00001, 50000.0, "BTCUSDT")
        assert qty == 0.0
