"""EventDrivenLoop 测试

EventDrivenLoop 依赖 axon_quant.agent.SwarmRunner 和交易所适配器,
通过 mock 隔离外部依赖, 测试核心事件处理逻辑。
"""

from unittest.mock import MagicMock, patch

from strategy.event_loop import EventDrivenLoop
from strategy.live_portfolio import LivePortfolio


class TestEventDrivenLoop:
    """EventDrivenLoop 单元测试"""

    def _make_loop(self, adapter=None, callback=None, initial_cash=100_000):
        """创建 EventDrivenLoop 实例。"""
        adapter = adapter or MagicMock()
        return EventDrivenLoop(
            adapter=adapter,
            symbol="BTCUSDT",
            initial_cash=initial_cash,
            risk_engine=None,
            event_callback=callback,
            enable_trajectory=False,
        )

    def _make_bar(self, close=50000.0) -> dict:
        """创建测试用 bar 数据。"""
        return {
            "open": close * 0.98,
            "high": close * 1.02,
            "low": close * 0.97,
            "close": close,
            "volume": 1000.0,
            "symbol": "BTCUSDT",
            "timestamp_ns": 1_000_000_000,
        }

    def test_init_creates_components(self):
        """初始化创建核心组件。"""
        loop = self._make_loop()
        assert loop.symbol == "BTCUSDT"
        assert isinstance(loop.portfolio, LivePortfolio)
        assert loop.portfolio.cash == 100_000
        assert loop.is_running is False

    def test_add_trader_returns_id(self):
        """添加 trader 返回 ID。"""
        loop = self._make_loop()
        trader = MagicMock()
        trader.id = "test_trader"
        trader.decide.return_value = {"action": "buy", "confidence": 0.8}
        tid = loop.add_trader(trader)
        assert tid == "test_trader"

    def test_remove_trader(self):
        """移除 trader。"""
        loop = self._make_loop()
        trader = MagicMock()
        trader.id = "removable"
        loop.add_trader(trader)
        assert loop.remove_trader("removable") is True
        assert loop.remove_trader("nonexistent") is False

    def test_process_bar_with_swarm(self):
        """手动处理单根 bar — Swarm 决策被正确执行。"""
        from axon_bridge import SwarmRunner

        loop = self._make_loop()
        trader = MagicMock()
        trader.id = "mock_trader"
        # trader 返回 buy 信号
        trader.decide.return_value = {
            "action": "buy",
            "confidence": 0.8,
            "reasoning": "test",
            "target_position": 0.1,
        }
        loop.add_trader(trader)

        # 构建 Swarm
        loop._swarm = SwarmRunner(traders=[trader])

        bar = self._make_bar(close=50000.0)
        stats = loop.process_bar(bar)

        assert stats["bar_count"] == 1
        assert stats["decision_count"] == 1
        assert stats["order_count"] == 1
        assert stats["fill_count"] == 1
        assert stats["last_price"] == 50000.0

    def test_process_bar_with_hold_no_order(self):
        """Hold 决策不产生订单。"""
        from axon_bridge import SwarmRunner

        loop = self._make_loop()
        trader = MagicMock()
        trader.id = "hold_trader"
        trader.decide.return_value = {
            "action": "hold",
            "confidence": 0.0,
            "reasoning": "no signal",
            "target_position": 0.0,
        }
        loop.add_trader(trader)
        loop._swarm = SwarmRunner(traders=[trader])

        bar = self._make_bar(close=50000.0)
        stats = loop.process_bar(bar)

        assert stats["order_count"] == 0
        assert stats["fill_count"] == 0
        assert stats["bar_count"] == 1

    def test_process_bar_multiple_bars(self):
        """处理多根 bar, 统计正确累计。"""
        from axon_bridge import SwarmRunner

        loop = self._make_loop()
        trader = MagicMock()
        trader.id = "multi_trader"
        trader.decide.return_value = {
            "action": "buy",
            "confidence": 0.7,
            "reasoning": "trend up",
            "target_position": 0.05,
        }
        loop.add_trader(trader)
        loop._swarm = SwarmRunner(traders=[trader])

        for i, close in enumerate([50000, 51000, 52000], 1):
            bar = self._make_bar(close=float(close))
            stats = loop.process_bar(bar)
            assert stats["bar_count"] == i
            assert stats["last_price"] == float(close)

        # 最终持仓应非空
        pf_dict = stats["portfolio"]
        assert pf_dict["total_fills"] == 3

    def test_event_callback_receives_events(self):
        """事件回调收到正确的事件类型。"""
        from axon_bridge import SwarmRunner

        events = []
        loop = self._make_loop(callback=lambda t, d: events.append((t, d)))

        trader = MagicMock()
        trader.id = "cb_trader"
        trader.decide.return_value = {
            "action": "buy",
            "confidence": 0.85,
            "reasoning": "strong signal",
            "target_position": 0.1,
        }
        loop.add_trader(trader)
        loop._swarm = SwarmRunner(traders=[trader])

        bar = self._make_bar(close=50000.0)
        loop.process_bar(bar)

        event_types = [e[0] for e in events]
        assert "bar.processed" in event_types
        assert "order.placed" in event_types
        assert "order.filled" in event_types

    def test_portfolio_state_after_trades(self):
        """交易后持仓状态正确。"""
        from axon_bridge import SwarmRunner

        loop = self._make_loop(initial_cash=100_000)
        trader = MagicMock()
        trader.id = "pf_trader"
        trader.decide.return_value = {
            "action": "buy",
            "confidence": 0.8,
            "reasoning": "buy",
            "target_position": 0.1,
        }
        loop.add_trader(trader)
        loop._swarm = SwarmRunner(traders=[trader])

        bar = self._make_bar(close=50000.0)
        stats = loop.process_bar(bar)

        pf = stats["portfolio"]
        assert pf["total_orders"] == 1
        assert pf["total_fills"] == 1
        assert pf["cash"] < 100_000  # 买入后现金减少
        # 持仓有 BTCUSDT
        assert "BTCUSDT" in pf["positions"]
        assert pf["positions"]["BTCUSDT"]["quantity"] > 0

    def test_stats_property(self):
        """stats 属性返回正确的 dict 结构。"""
        loop = self._make_loop()
        stats = loop.stats
        assert "symbol" in stats
        assert "bar_count" in stats
        assert "decision_count" in stats
        assert "order_count" in stats
        assert "fill_count" in stats
        assert "rejected_count" in stats
        assert "last_price" in stats
        assert "last_decision" in stats
        assert "circuit_broken" in stats
        assert "portfolio" in stats
        assert stats["symbol"] == "BTCUSDT"

    def test_start_requires_trader(self):
        """无 trader 时 start() 抛异常。"""
        loop = self._make_loop()
        try:
            loop.start()
            raise AssertionError("应该抛出 RuntimeError")
        except RuntimeError as e:
            assert "trader" in str(e).lower() or "Trader" in str(e)

    def test_start_stop_lifecycle(self):
        """完整启动-停止生命周期。"""
        from axon_bridge import SwarmRunner

        loop = self._make_loop()
        trader = MagicMock()
        trader.id = "lifecycle_trader"
        trader.decide.return_value = {
            "action": "buy",
            "confidence": 0.7,
            "reasoning": "test",
            "target_position": 0.1,
        }
        loop.add_trader(trader)

        # 用 Mock 替换 SwarmRunner 构建和线程
        mock_swarm = MagicMock()
        mock_swarm.on_bar.return_value = {
            "final_action": "Buy",
            "final_confidence": 1.0,
            "votes": [],
            "aggregated": {},
            "risk_verdict": {"approved": True},
        }
        # Mock 线程: 让 is_alive() 始终返回 True
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True

        with patch.object(loop, "_build_swarm", return_value=mock_swarm):
            with patch("threading.Thread", return_value=mock_thread):
                loop.start()

        assert loop.is_running is True
        assert loop._swarm is mock_swarm
        trader.on_start.assert_called_once()

        loop.stop()
        assert loop.is_running is False
        trader.on_stop.assert_called_once()

    def test_sell_decision_reduces_position(self):
        """卖出决策正确执行 (先买后卖)。"""
        from axon_bridge import SwarmRunner

        loop = self._make_loop()
        trader = MagicMock()
        trader.id = "bs_trader"
        loop.add_trader(trader)

        # 先买入
        trader.decide.return_value = {
            "action": "buy",
            "confidence": 0.8,
            "reasoning": "first buy",
            "target_position": 0.15,
        }
        loop._swarm = SwarmRunner(traders=[trader])
        bar = self._make_bar(close=50000.0)
        loop.process_bar(bar)

        # 再卖出
        trader.decide.return_value = {
            "action": "sell",
            "confidence": 0.6,
            "reasoning": "take profit",
            "target_position": -0.15,
        }
        bar2 = self._make_bar(close=55000.0)
        stats = loop.process_bar(bar2)

        pf = stats["portfolio"]
        assert pf["total_fills"] == 2
        # 最终应该是 close position 或接近 flat
        pos = pf["positions"].get("BTCUSDT", {})
        # 卖出后持仓减少
        if pos:
            assert pos.get("quantity", 0) < 0.15  # 持仓减少

    def test_multiple_traders_consensus(self):
        """多个 trader 投票共识。"""
        from axon_bridge import SwarmRunner

        loop = self._make_loop()

        # 3 个 trader: 2 个买入, 1 个卖出
        for i, action in enumerate(["buy", "buy", "sell"]):
            trader = MagicMock()
            trader.id = f"trader_{i}"
            trader.decide.return_value = {
                "action": action,
                "confidence": 0.7,
                "reasoning": f"signal {action}",
                "target_position": 0.1 if action == "buy" else 0.0,
            }
            loop.add_trader(trader)

        traders = loop._trader_registry.get_all()
        swarm = SwarmRunner(traders=traders)
        loop._swarm = swarm

        bar = self._make_bar(close=50000.0)
        stats = loop.process_bar(bar)

        # 2/3 投票买入, SwarmRunner 应该聚合为买入
        decision = stats["last_decision"]
        assert decision is not None
        # aggregated 应有买入倾向
        aggregated = decision.get("aggregated", {})
        assert aggregated.get("action", "").lower() == "buy"
