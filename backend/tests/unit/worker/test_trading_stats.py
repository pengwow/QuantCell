"""
Worker 交易统计功能单元测试

覆盖范围：
1. 增强版交易查询 - 多维度筛选
2. 订单查询 - 多维度筛选
3. 持仓查询 - 多维度筛选
4. 交易汇总统计 - 优化版
5. 盈亏分布计算
6. 交易历史图表数据

运行方式：
    cd backend && uv run pytest tests/unit/worker/test_trading_stats.py -v
"""

import pytest
from datetime import datetime, timedelta
from worker import crud
from worker.models import WorkerTrade, WorkerOrder, WorkerPosition


class TestEnhancedTradeQuery:
    """增强版交易查询测试"""

    def test_get_worker_trades_paginated_basic(self, db_session):
        """基础分页查询"""
        worker_id = 1
        for i in range(5):
            trade = WorkerTrade(
                worker_id=worker_id,
                trade_id=f"trade-{i}",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1.0,
                price=50000.0,
                amount=50000.0,
                realized_pnl=100.0,
            )
            db_session.add(trade)
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(db_session, worker_id)
        assert total == 5
        assert len(trades) == 5

    def test_get_worker_trades_paginated_symbol_filter(self, db_session):
        """按交易对筛选"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="ETHUSDT",
            side="buy", order_type="market", quantity=1, price=3000, amount=3000,
        ))
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(db_session, worker_id, symbol="BTCUSDT")
        assert total == 1
        assert trades[0].symbol == "BTCUSDT"

    def test_get_worker_trades_paginated_side_filter(self, db_session):
        """按方向筛选"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="sell", order_type="market", quantity=1, price=51000, amount=51000,
        ))
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(db_session, worker_id, side="sell")
        assert total == 1
        assert trades[0].side == "sell"

    def test_get_worker_trades_paginated_order_type_filter(self, db_session):
        """按订单类型筛选"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="buy", order_type="limit", quantity=1, price=49000, amount=49000,
        ))
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(db_session, worker_id, order_type="limit")
        assert total == 1
        assert trades[0].order_type == "limit"

    def test_get_worker_trades_paginated_pnl_status_filter(self, db_session):
        """按盈亏状态筛选"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="sell", order_type="market", quantity=1, price=49000, amount=49000,
            realized_pnl=-50.0,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t3", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=0.0,
        ))
        db_session.commit()

        profit_trades, _ = crud.get_worker_trades_paginated(db_session, worker_id, pnl_status="profit")
        assert len(profit_trades) == 1
        assert profit_trades[0].realized_pnl > 0

        loss_trades, _ = crud.get_worker_trades_paginated(db_session, worker_id, pnl_status="loss")
        assert len(loss_trades) == 1
        assert loss_trades[0].realized_pnl < 0

        flat_trades, _ = crud.get_worker_trades_paginated(db_session, worker_id, pnl_status="flat")
        assert len(flat_trades) == 1
        assert flat_trades[0].realized_pnl == 0

    def test_get_worker_trades_paginated_time_range(self, db_session):
        """按时间范围筛选"""
        worker_id = 1
        now = datetime.now()
        old_trade = WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
        )
        old_trade.created_at = now - timedelta(days=10)
        db_session.add(old_trade)

        new_trade = WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=51000, amount=51000,
        )
        new_trade.created_at = now - timedelta(days=1)
        db_session.add(new_trade)
        db_session.commit()

        start = now - timedelta(days=5)
        end = now
        trades, total = crud.get_worker_trades_paginated(
            db_session, worker_id, start_time=start, end_time=end
        )
        assert total == 1
        assert trades[0].trade_id == "t2"

    def test_get_worker_trades_paginated_combined_filters(self, db_session):
        """组合筛选条件"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="ETHUSDT",
            side="buy", order_type="limit", quantity=1, price=3000, amount=3000,
            realized_pnl=50.0,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t3", symbol="BTCUSDT",
            side="sell", order_type="market", quantity=1, price=51000, amount=51000,
            realized_pnl=-30.0,
        ))
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(
            db_session, worker_id, symbol="BTCUSDT", side="buy", pnl_status="profit"
        )
        assert total == 1
        assert trades[0].trade_id == "t1"

    def test_get_worker_trades_paginated_empty_result(self, db_session):
        """无结果返回空列表"""
        trades, total = crud.get_worker_trades_paginated(db_session, 999)
        assert total == 0
        assert trades == []


class TestOrderQuery:
    """订单查询测试"""

    def test_get_worker_orders_paginated_basic(self, db_session):
        """基础订单分页查询"""
        worker_id = 1
        for i in range(5):
            order = WorkerOrder(
                worker_id=worker_id,
                client_order_id=f"order-{i}",
                symbol="BTCUSDT",
                side="BUY",
                order_type="MARKET",
                quantity=1.0,
                status="FILLED",
            )
            db_session.add(order)
        db_session.commit()

        orders, total = crud.get_worker_orders_paginated(db_session, worker_id)
        assert total == 5
        assert len(orders) == 5

    def test_get_worker_orders_paginated_status_filter(self, db_session):
        """按状态筛选"""
        worker_id = 1
        db_session.add(WorkerOrder(
            worker_id=worker_id, client_order_id="o1", symbol="BTCUSDT",
            side="BUY", order_type="MARKET", quantity=1, status="FILLED",
        ))
        db_session.add(WorkerOrder(
            worker_id=worker_id, client_order_id="o2", symbol="BTCUSDT",
            side="BUY", order_type="MARKET", quantity=1, status="CANCELED",
        ))
        db_session.commit()

        orders, total = crud.get_worker_orders_paginated(db_session, worker_id, status="CANCELED")
        assert total == 1
        assert orders[0].status == "CANCELED"

    def test_get_worker_orders_paginated_symbol_filter(self, db_session):
        """按交易对筛选"""
        worker_id = 1
        db_session.add(WorkerOrder(
            worker_id=worker_id, client_order_id="o1", symbol="BTCUSDT",
            side="BUY", order_type="MARKET", quantity=1, status="FILLED",
        ))
        db_session.add(WorkerOrder(
            worker_id=worker_id, client_order_id="o2", symbol="ETHUSDT",
            side="BUY", order_type="MARKET", quantity=1, status="FILLED",
        ))
        db_session.commit()

        orders, total = crud.get_worker_orders_paginated(db_session, worker_id, symbol="ETHUSDT")
        assert total == 1
        assert orders[0].symbol == "ETHUSDT"

    def test_get_worker_orders_paginated_combined_filters(self, db_session):
        """组合筛选条件"""
        worker_id = 1
        db_session.add(WorkerOrder(
            worker_id=worker_id, client_order_id="o1", symbol="BTCUSDT",
            side="BUY", order_type="MARKET", quantity=1, status="FILLED",
        ))
        db_session.add(WorkerOrder(
            worker_id=worker_id, client_order_id="o2", symbol="BTCUSDT",
            side="SELL", order_type="LIMIT", quantity=1, status="OPEN",
        ))
        db_session.commit()

        orders, total = crud.get_worker_orders_paginated(
            db_session, worker_id, symbol="BTCUSDT", side="SELL", status="OPEN"
        )
        assert total == 1
        assert orders[0].client_order_id == "o2"


class TestPositionQuery:
    """持仓查询测试"""

    def test_get_worker_positions_filtered_default_open(self, db_session):
        """默认只返回OPEN持仓"""
        worker_id = 1
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p1", symbol="BTCUSDT",
            side="LONG", quantity=1.0, entry_price=50000.0, status="OPEN",
        ))
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p2", symbol="ETHUSDT",
            side="LONG", quantity=1.0, entry_price=3000.0, status="CLOSED",
        ))
        db_session.commit()

        positions = crud.get_worker_positions_filtered(db_session, worker_id)
        assert len(positions) == 1
        assert positions[0].status == "OPEN"

    def test_get_worker_positions_filtered_by_status(self, db_session):
        """按状态筛选"""
        worker_id = 1
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p1", symbol="BTCUSDT",
            side="LONG", quantity=1.0, entry_price=50000.0, status="OPEN",
        ))
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p2", symbol="ETHUSDT",
            side="LONG", quantity=1.0, entry_price=3000.0, status="CLOSED",
        ))
        db_session.commit()

        positions = crud.get_worker_positions_filtered(db_session, worker_id, status="CLOSED")
        assert len(positions) == 1
        assert positions[0].status == "CLOSED"

    def test_get_worker_positions_filtered_by_symbol(self, db_session):
        """按交易对筛选"""
        worker_id = 1
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p1", symbol="BTCUSDT",
            side="LONG", quantity=1.0, entry_price=50000.0, status="OPEN",
        ))
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p2", symbol="ETHUSDT",
            side="LONG", quantity=1.0, entry_price=3000.0, status="OPEN",
        ))
        db_session.commit()

        positions = crud.get_worker_positions_filtered(db_session, worker_id, symbol="ETHUSDT")
        assert len(positions) == 1
        assert positions[0].symbol == "ETHUSDT"

    def test_get_worker_positions_filtered_by_side(self, db_session):
        """按方向筛选"""
        worker_id = 1
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p1", symbol="BTCUSDT",
            side="LONG", quantity=1.0, entry_price=50000.0, status="OPEN",
        ))
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p2", symbol="BTCUSDT",
            side="SHORT", quantity=1.0, entry_price=51000.0, status="OPEN",
        ))
        db_session.commit()

        positions = crud.get_worker_positions_filtered(db_session, worker_id, side="SHORT")
        assert len(positions) == 1
        assert positions[0].side == "SHORT"

    def test_get_worker_positions_filtered_empty(self, db_session):
        """无持仓返回空列表"""
        positions = crud.get_worker_positions_filtered(db_session, 999)
        assert positions == []


class TestTradingSummary:
    """交易汇总统计测试"""

    def test_get_trading_summary_empty(self, db_session):
        """无交易记录返回零值"""
        result = crud.get_trading_summary(db_session, 1)
        assert result["total_trades"] == 0
        assert result["total_pnl"] == 0.0
        assert result["win_rate"] == 0.0

    def test_get_trading_summary_basic(self, db_session):
        """基础统计计算"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0, fee=5.0,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="sell", order_type="market", quantity=1, price=51000, amount=51000,
            realized_pnl=-30.0, fee=5.0,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t3", symbol="ETHUSDT",
            side="buy", order_type="limit", quantity=1, price=3000, amount=3000,
            realized_pnl=50.0, fee=3.0,
        ))
        db_session.commit()

        result = crud.get_trading_summary(db_session, worker_id)
        assert result["total_trades"] == 3
        assert result["winning_trades"] == 2
        assert result["losing_trades"] == 1
        assert result["total_pnl"] == 120.0
        assert result["total_profit"] == 150.0
        assert result["total_loss"] == -30.0
        assert result["win_rate"] == pytest.approx(66.67, 0.01)
        assert result["profit_factor"] == pytest.approx(5.0, 0.01)
        assert result["largest_profit"] == 100.0
        assert result["largest_loss"] == -30.0
        assert result["total_volume"] == 104000.0
        assert result["total_fees"] == 13.0

    def test_get_trading_summary_optimized_empty(self, db_session):
        """优化版无记录返回零值"""
        result = crud.get_trading_summary_optimized(db_session, 1)
        assert result["total_trades"] == 0
        assert result["total_pnl"] == 0.0

    def test_get_trading_summary_optimized_basic(self, db_session):
        """优化版基础统计"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0, fee=5.0,
        ))
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="sell", order_type="market", quantity=1, price=49000, amount=49000,
            realized_pnl=-50.0, fee=5.0,
        ))
        db_session.commit()

        result = crud.get_trading_summary_optimized(db_session, worker_id)
        assert result["total_trades"] == 2
        assert result["winning_trades"] == 1
        assert result["losing_trades"] == 1
        assert result["total_pnl"] == 50.0
        assert result["total_profit"] == 100.0
        assert result["total_loss"] == -50.0

    def test_get_trading_summary_optimized_time_filter(self, db_session):
        """优化版时间范围过滤"""
        worker_id = 1
        now = datetime.now()

        old_trade = WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0,
        )
        old_trade.created_at = now - timedelta(days=10)
        db_session.add(old_trade)

        new_trade = WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="sell", order_type="market", quantity=1, price=51000, amount=51000,
            realized_pnl=50.0,
        )
        new_trade.created_at = now - timedelta(days=1)
        db_session.add(new_trade)
        db_session.commit()

        start = now - timedelta(days=5)
        result = crud.get_trading_summary_optimized(db_session, worker_id, start_time=start)
        assert result["total_trades"] == 1
        assert result["total_pnl"] == 50.0


class TestPnLDistribution:
    """盈亏分布测试"""

    def test_get_pnl_distribution_empty(self, db_session):
        """无交易记录"""
        result = crud.get_pnl_distribution(db_session, 1)
        assert result["bins"] == []
        assert result["counts"] == []
        assert result["mean"] == 0.0

    def test_get_pnl_distribution_basic(self, db_session):
        """基础盈亏分布"""
        worker_id = 1
        pnl_values = [100, 50, 200, -30, -80, 150, -20, 0]
        for i, pnl in enumerate(pnl_values):
            db_session.add(WorkerTrade(
                worker_id=worker_id, trade_id=f"t{i}", symbol="BTCUSDT",
                side="buy", order_type="market", quantity=1, price=50000, amount=50000,
                realized_pnl=float(pnl),
            ))
        db_session.commit()

        result = crud.get_pnl_distribution(db_session, worker_id)
        assert len(result["bins"]) > 0
        assert len(result["counts"]) > 0
        assert sum(result["counts"]) == len(pnl_values)
        assert result["mean"] != 0.0


class TestTradeHistoryChart:
    """交易历史图表数据测试"""

    def test_get_trade_history_chart_empty(self, db_session):
        """无交易记录"""
        result = crud.get_trade_history_chart(db_session, 1, days=30)
        assert result["dates"] == []
        assert result["cumulative_pnl"] == []

    def test_get_trade_history_chart_basic(self, db_session):
        """基础历史数据"""
        worker_id = 1
        now = datetime.now()

        day1 = now - timedelta(days=2)
        t1 = WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0,
        )
        t1.created_at = day1
        db_session.add(t1)

        day2 = now - timedelta(days=1)
        t2 = WorkerTrade(
            worker_id=worker_id, trade_id="t2", symbol="BTCUSDT",
            side="sell", order_type="market", quantity=1, price=51000, amount=51000,
            realized_pnl=-50.0,
        )
        t2.created_at = day2
        db_session.add(t2)

        t3 = WorkerTrade(
            worker_id=worker_id, trade_id="t3", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=80.0,
        )
        t3.created_at = day2
        db_session.add(t3)
        db_session.commit()

        result = crud.get_trade_history_chart(db_session, worker_id, days=7)
        assert len(result["dates"]) > 0
        assert len(result["cumulative_pnl"]) > 0
        assert len(result["daily_pnl"]) > 0
        assert len(result["trade_count"]) > 0
        assert result["cumulative_pnl"][-1] == 130.0


class TestTradingStatsService:
    """TradingStatsService测试"""

    def test_get_position_summary_empty(self, db_session):
        """无持仓时返回零值"""
        from worker.stats_service import TradingStatsService
        service = TradingStatsService(db_session)
        result = service.get_position_summary(1)
        assert result["total_positions"] == 0
        assert result["long_positions"] == 0
        assert result["short_positions"] == 0
        assert result["total_value"] == 0.0
        assert result["total_unrealized_pnl"] == 0.0
        assert result["total_margin_used"] == 0.0
        assert result["positions"] == []

    def test_get_position_summary_basic(self, db_session):
        """基本持仓统计"""
        from worker.stats_service import TradingStatsService
        worker_id = 1
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p1", symbol="BTCUSDT",
            side="LONG", quantity=1.0, entry_price=50000.0, current_price=51000.0,
            unrealized_pnl=1000.0, margin_used=5000.0, status="OPEN",
        ))
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="p2", symbol="ETHUSDT",
            side="SHORT", quantity=5.0, entry_price=3000.0, current_price=2950.0,
            unrealized_pnl=250.0, margin_used=7500.0, status="OPEN",
        ))
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_position_summary(worker_id)
        assert result["total_positions"] == 2
        assert result["long_positions"] == 1
        assert result["short_positions"] == 1
        assert result["total_value"] == pytest.approx(1.0*51000 +5.0*2950, 0.01)
        assert result["total_unrealized_pnl"] == 1250.0
        assert result["total_margin_used"] == 12500.0
        assert len(result["positions"]) == 2

    def test_get_trading_summary_via_service(self, db_session):
        """通过service获取交易汇总"""
        from worker.stats_service import TradingStatsService
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0,
        ))
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_trading_summary(worker_id)
        assert result["total_trades"] == 1
        assert result["winning_trades"] ==1

    def test_get_pnl_distribution_via_service(self, db_session):
        """通过service获取盈亏分布"""
        from worker.stats_service import TradingStatsService
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0,
        ))
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_pnl_distribution(worker_id)
        assert result["mean"] != 0.0

    def test_get_trade_history_chart_via_service(self, db_session):
        """通过service获取交易历史图表"""
        from worker.stats_service import TradingStatsService
        worker_id =1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="t1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
            realized_pnl=100.0,
        ))
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_trade_history_chart(worker_id)
        assert len(result["dates"]) >=0


class TestDataIntegrity:
    """数据完整性测试"""

    def test_trade_id_uniqueness(self, db_session):
        """交易ID唯一性"""
        worker_id = 1
        db_session.add(WorkerTrade(
            worker_id=worker_id, trade_id="unique-1", symbol="BTCUSDT",
            side="buy", order_type="market", quantity=1, price=50000, amount=50000,
        ))
        db_session.commit()

        duplicate = WorkerTrade(
            worker_id=worker_id, trade_id="unique-1", symbol="ETHUSDT",
            side="buy", order_type="market", quantity=1, price=3000, amount=3000,
        )
        db_session.add(duplicate)

        with pytest.raises(Exception):
            db_session.commit()

    def test_order_client_order_id_uniqueness(self, db_session):
        """订单client_order_id唯一性"""
        worker_id = 1
        db_session.add(WorkerOrder(
            worker_id=worker_id, client_order_id="order-1", symbol="BTCUSDT",
            side="BUY", order_type="MARKET", quantity=1, status="FILLED",
        ))
        db_session.commit()

        duplicate = WorkerOrder(
            worker_id=worker_id, client_order_id="order-1", symbol="ETHUSDT",
            side="BUY", order_type="MARKET", quantity=1, status="FILLED",
        )
        db_session.add(duplicate)

        with pytest.raises(Exception):
            db_session.commit()

    def test_position_position_id_uniqueness(self, db_session):
        """持仓position_id唯一性"""
        worker_id = 1
        db_session.add(WorkerPosition(
            worker_id=worker_id, position_id="pos-1", symbol="BTCUSDT",
            side="LONG", quantity=1.0, entry_price=50000.0, status="OPEN",
        ))
        db_session.commit()

        duplicate = WorkerPosition(
            worker_id=worker_id, position_id="pos-1", symbol="ETHUSDT",
            side="LONG", quantity=1.0, entry_price=3000.0, status="OPEN",
        )
        db_session.add(duplicate)

        with pytest.raises(Exception):
            db_session.commit()
