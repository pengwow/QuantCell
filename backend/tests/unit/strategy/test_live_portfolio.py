"""LivePortfolio 测试"""

from strategy.live_portfolio import LivePortfolio, Position


class TestPosition:
    """Position 持仓更新测试"""

    def test_new_position_long(self):
        """新开多仓"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("buy", 1.0, 50000.0)
        assert pos.quantity == 1.0
        assert pos.side == "long"
        assert pos.avg_price == 50000.0
        assert pos.realized_pnl == 0.0

    def test_add_to_long(self):
        """加仓多仓"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("buy", 1.0, 50000.0)
        pos.update_on_fill("buy", 0.5, 52000.0)
        assert pos.quantity == 1.5
        # 均价 = (50000*1 + 52000*0.5) / 1.5 = 50666.67
        assert abs(pos.avg_price - 50666.67) < 0.01
        assert pos.side == "long"

    def test_close_partial_long(self):
        """部分平多"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("buy", 1.0, 50000.0)
        pos.update_on_fill("sell", 0.3, 55000.0)  # 盈利 1500
        assert pos.quantity == 0.7
        assert pos.side == "long"
        # 已实现盈亏 = (55000-50000)*0.3 = 1500
        assert abs(pos.realized_pnl - 1500.0) < 0.01

    def test_close_full_long_profit(self):
        """全平多仓 (盈利)"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("buy", 1.0, 50000.0)
        pos.update_on_fill("sell", 1.0, 55000.0)
        assert pos.quantity == 0.0
        assert pos.side == "flat"
        assert abs(pos.realized_pnl - 5000.0) < 0.01

    def test_close_full_long_loss(self):
        """全平多仓 (亏损)"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("buy", 1.0, 50000.0)
        pos.update_on_fill("sell", 1.0, 48000.0)
        assert pos.quantity == 0.0
        assert pos.side == "flat"
        assert abs(pos.realized_pnl - (-2000.0)) < 0.01

    def test_open_short(self):
        """开空仓"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("sell", 1.0, 50000.0)
        assert pos.quantity == -1.0
        assert pos.side == "short"
        assert pos.avg_price == 50000.0

    def test_mark_to_market_long(self):
        """按市值计价 (多仓)"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("buy", 1.0, 50000.0)
        pos.mark_to_market(55000.0)
        assert abs(pos.unrealized_pnl - 5000.0) < 0.01

    def test_mark_to_market_short(self):
        """按市值计价 (空仓)"""
        pos = Position(symbol="BTCUSDT")
        pos.update_on_fill("sell", 1.0, 50000.0)
        pos.mark_to_market(45000.0)
        # 空仓盈利 = (50000-45000)*1 = 5000
        assert abs(pos.unrealized_pnl - 5000.0) < 0.01


class TestLivePortfolio:
    """LivePortfolio 组合测试"""

    def test_initial_cash(self):
        """初始资金设置"""
        pf = LivePortfolio(initial_cash=100_000)
        assert pf.cash == 100_000
        assert pf.initial_cash == 100_000

    def test_get_position_creates(self):
        """get_position 自动创建"""
        pf = LivePortfolio(initial_cash=100_000)
        pos = pf.get_position("BTCUSDT")
        assert pos.symbol == "BTCUSDT"
        assert pos.quantity == 0.0

    def test_update_on_fill_buy(self):
        """买入更新持仓和现金"""
        pf = LivePortfolio(initial_cash=100_000)
        pf.update_on_fill("BTCUSDT", "buy", 1.0, 50000.0, fee=20.0)
        assert pf.total_fills == 1
        assert pf.total_fees == 20.0
        # 现金 = 100000 - 50000 - 20 = 49980
        assert abs(pf.cash - 49980.0) < 0.01
        pos = pf.get_position("BTCUSDT")
        assert pos.quantity == 1.0

    def test_update_on_fill_sell(self):
        """卖出更新持仓和现金"""
        pf = LivePortfolio(initial_cash=100_000)
        pf.update_on_fill("BTCUSDT", "sell", 1.0, 55000.0, fee=22.0)
        assert pf.total_fills == 1
        assert pf.total_fees == 22.0
        # 现金 = 100000 + 55000 - 22 = 154978
        assert abs(pf.cash - 154978.0) < 0.01
        pos = pf.get_position("BTCUSDT")
        assert pos.quantity == -1.0

    def test_mark_to_market_equity(self):
        """按市值计算总权益"""
        pf = LivePortfolio(initial_cash=100_000)
        pf.update_on_fill("BTCUSDT", "buy", 1.0, 50000.0)
        # 权益 = 现金(50000) + 持仓市值(1*55000) = 105000
        equity = pf.mark_to_market({"BTCUSDT": 55000.0})
        assert abs(equity - 105000.0) < 0.01

    def test_to_dict(self):
        """序列化为 dict"""
        pf = LivePortfolio(initial_cash=100_000)
        pf.update_on_fill("BTCUSDT", "buy", 1.0, 50000.0)
        d = pf.to_dict()
        assert "cash" in d
        assert "positions" in d
        assert "BTCUSDT" in d["positions"]
        assert d["positions"]["BTCUSDT"]["quantity"] == 1.0
