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

from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from worker import crud
from worker.models import WorkerOrder, WorkerPosition, WorkerTrade


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
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t2",
                symbol="ETHUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=3000,
                amount=3000,
            )
        )
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(db_session, worker_id, symbol="BTCUSDT")
        assert total == 1
        assert trades[0].symbol == "BTCUSDT"

    def test_get_worker_trades_paginated_side_filter(self, db_session):
        """按方向筛选"""
        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t2",
                symbol="BTCUSDT",
                side="sell",
                order_type="market",
                quantity=1,
                price=51000,
                amount=51000,
            )
        )
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(db_session, worker_id, side="sell")
        assert total == 1
        assert trades[0].side == "sell"

    def test_get_worker_trades_paginated_order_type_filter(self, db_session):
        """按订单类型筛选"""
        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t2",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=1,
                price=49000,
                amount=49000,
            )
        )
        db_session.commit()

        trades, total = crud.get_worker_trades_paginated(db_session, worker_id, order_type="limit")
        assert total == 1
        assert trades[0].order_type == "limit"

    def test_get_worker_trades_paginated_pnl_status_filter(self, db_session):
        """按盈亏状态筛选"""
        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=100.0,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t2",
                symbol="BTCUSDT",
                side="sell",
                order_type="market",
                quantity=1,
                price=49000,
                amount=49000,
                realized_pnl=-50.0,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t3",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=0.0,
            )
        )
        # t4 模拟开仓 fill：引擎尚未配对出 round-trip，realized_pnl 未回填
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t4",
                symbol="BTCUSDT",
                side="sell",
                order_type="market",
                quantity=1,
                price=51000,
                amount=51000,
                realized_pnl=None,
            )
        )
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

        # open = entry fill 行（realized_pnl 为 None）；closed = 已回填配对盈亏的行
        open_trades, open_total = crud.get_worker_trades_paginated(db_session, worker_id, pnl_status="open")
        assert open_total == 1
        assert open_trades[0].realized_pnl is None

        closed_trades, closed_total = crud.get_worker_trades_paginated(db_session, worker_id, pnl_status="closed")
        assert closed_total == 3
        assert len(closed_trades) == 3
        assert all(t.realized_pnl is not None for t in closed_trades)

    def test_get_worker_trades_paginated_time_range(self, db_session):
        """按时间范围筛选"""
        worker_id = 1
        now = datetime.now()
        old_trade = WorkerTrade(
            worker_id=worker_id,
            trade_id="t1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=50000,
            amount=50000,
        )
        old_trade.created_at = now - timedelta(days=10)
        db_session.add(old_trade)

        new_trade = WorkerTrade(
            worker_id=worker_id,
            trade_id="t2",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=51000,
            amount=51000,
        )
        new_trade.created_at = now - timedelta(days=1)
        db_session.add(new_trade)
        db_session.commit()

        start = now - timedelta(days=5)
        end = now
        trades, total = crud.get_worker_trades_paginated(db_session, worker_id, start_time=start, end_time=end)
        assert total == 1
        assert trades[0].trade_id == "t2"

    def test_get_worker_trades_paginated_combined_filters(self, db_session):
        """组合筛选条件"""
        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=100.0,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t2",
                symbol="ETHUSDT",
                side="buy",
                order_type="limit",
                quantity=1,
                price=3000,
                amount=3000,
                realized_pnl=50.0,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t3",
                symbol="BTCUSDT",
                side="sell",
                order_type="market",
                quantity=1,
                price=51000,
                amount=51000,
                realized_pnl=-30.0,
            )
        )
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
                side="buy",
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
        db_session.add(
            WorkerOrder(
                worker_id=worker_id,
                client_order_id="o1",
                symbol="BTCUSDT",
                side="buy",
                order_type="MARKET",
                quantity=1,
                status="FILLED",
            )
        )
        db_session.add(
            WorkerOrder(
                worker_id=worker_id,
                client_order_id="o2",
                symbol="BTCUSDT",
                side="buy",
                order_type="MARKET",
                quantity=1,
                status="CANCELED",
            )
        )
        db_session.commit()

        orders, total = crud.get_worker_orders_paginated(db_session, worker_id, status="CANCELED")
        assert total == 1
        assert orders[0].status == "CANCELED"

    def test_get_worker_orders_paginated_symbol_filter(self, db_session):
        """按交易对筛选"""
        worker_id = 1
        db_session.add(
            WorkerOrder(
                worker_id=worker_id,
                client_order_id="o1",
                symbol="BTCUSDT",
                side="buy",
                order_type="MARKET",
                quantity=1,
                status="FILLED",
            )
        )
        db_session.add(
            WorkerOrder(
                worker_id=worker_id,
                client_order_id="o2",
                symbol="ETHUSDT",
                side="buy",
                order_type="MARKET",
                quantity=1,
                status="FILLED",
            )
        )
        db_session.commit()

        orders, total = crud.get_worker_orders_paginated(db_session, worker_id, symbol="ETHUSDT")
        assert total == 1
        assert orders[0].symbol == "ETHUSDT"

    def test_get_worker_orders_paginated_combined_filters(self, db_session):
        """组合筛选条件"""
        worker_id = 1
        db_session.add(
            WorkerOrder(
                worker_id=worker_id,
                client_order_id="o1",
                symbol="BTCUSDT",
                side="buy",
                order_type="MARKET",
                quantity=1,
                status="FILLED",
            )
        )
        db_session.add(
            WorkerOrder(
                worker_id=worker_id,
                client_order_id="o2",
                symbol="BTCUSDT",
                side="sell",
                order_type="LIMIT",
                quantity=1,
                status="OPEN",
            )
        )
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
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p1",
                symbol="BTCUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=50000.0,
                status="OPEN",
            )
        )
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p2",
                symbol="ETHUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=3000.0,
                status="CLOSED",
            )
        )
        db_session.commit()

        positions = crud.get_worker_positions_filtered(db_session, worker_id)
        assert len(positions) == 1
        assert positions[0].status == "OPEN"

    def test_get_worker_positions_filtered_by_status(self, db_session):
        """按状态筛选"""
        worker_id = 1
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p1",
                symbol="BTCUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=50000.0,
                status="OPEN",
            )
        )
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p2",
                symbol="ETHUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=3000.0,
                status="CLOSED",
            )
        )
        db_session.commit()

        positions = crud.get_worker_positions_filtered(db_session, worker_id, status="CLOSED")
        assert len(positions) == 1
        assert positions[0].status == "CLOSED"

    def test_get_worker_positions_filtered_by_symbol(self, db_session):
        """按交易对筛选"""
        worker_id = 1
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p1",
                symbol="BTCUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=50000.0,
                status="OPEN",
            )
        )
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p2",
                symbol="ETHUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=3000.0,
                status="OPEN",
            )
        )
        db_session.commit()

        positions = crud.get_worker_positions_filtered(db_session, worker_id, symbol="ETHUSDT")
        assert len(positions) == 1
        assert positions[0].symbol == "ETHUSDT"

    def test_get_worker_positions_filtered_by_side(self, db_session):
        """按方向筛选"""
        worker_id = 1
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p1",
                symbol="BTCUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=50000.0,
                status="OPEN",
            )
        )
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p2",
                symbol="BTCUSDT",
                position_side="short",
                quantity=1.0,
                entry_price=51000.0,
                status="OPEN",
            )
        )
        db_session.commit()

        # 筛选参数条件性保留大写：验证 crud 对查询参数大小写不敏感（vocab 归一）
        positions = crud.get_worker_positions_filtered(db_session, worker_id, side="SHORT")
        assert len(positions) == 1
        assert positions[0].position_side == "short"

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
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=100.0,
                fee=5.0,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t2",
                symbol="BTCUSDT",
                side="sell",
                order_type="market",
                quantity=1,
                price=51000,
                amount=51000,
                realized_pnl=-30.0,
                fee=5.0,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t3",
                symbol="ETHUSDT",
                side="buy",
                order_type="limit",
                quantity=1,
                price=3000,
                amount=3000,
                realized_pnl=50.0,
                fee=3.0,
            )
        )
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
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=100.0,
                fee=5.0,
            )
        )
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t2",
                symbol="BTCUSDT",
                side="sell",
                order_type="market",
                quantity=1,
                price=49000,
                amount=49000,
                realized_pnl=-50.0,
                fee=5.0,
            )
        )
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
            worker_id=worker_id,
            trade_id="t1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=50000,
            amount=50000,
            realized_pnl=100.0,
        )
        old_trade.created_at = now - timedelta(days=10)
        db_session.add(old_trade)

        new_trade = WorkerTrade(
            worker_id=worker_id,
            trade_id="t2",
            symbol="BTCUSDT",
            side="sell",
            order_type="market",
            quantity=1,
            price=51000,
            amount=51000,
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
            db_session.add(
                WorkerTrade(
                    worker_id=worker_id,
                    trade_id=f"t{i}",
                    symbol="BTCUSDT",
                    side="buy",
                    order_type="market",
                    quantity=1,
                    price=50000,
                    amount=50000,
                    realized_pnl=float(pnl),
                )
            )
        db_session.commit()

        result = crud.get_pnl_distribution(db_session, worker_id)
        assert len(result["bins"]) > 0
        assert len(result["counts"]) > 0
        assert sum(result["counts"]) == len(pnl_values)
        assert result["mean"] != 0.0

    def test_get_pnl_distribution_start_time_filter(self, db_session):
        """start_time 过滤：总览页切换时间档时盈亏分布必须随之收窄"""
        worker_id = 1
        now = datetime.now()

        old_trade = WorkerTrade(
            worker_id=worker_id,
            trade_id="t1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=50000,
            amount=50000,
            realized_pnl=100.0,
        )
        old_trade.created_at = now - timedelta(days=10)
        db_session.add(old_trade)

        new_trade = WorkerTrade(
            worker_id=worker_id,
            trade_id="t2",
            symbol="BTCUSDT",
            side="sell",
            order_type="market",
            quantity=1,
            price=51000,
            amount=51000,
            realized_pnl=50.0,
        )
        new_trade.created_at = now - timedelta(days=1)
        db_session.add(new_trade)
        db_session.commit()

        # 不传 start_time = 全量（独立分布端点保持原口径）
        full = crud.get_pnl_distribution(db_session, worker_id)
        assert sum(full["counts"]) == 2

        # 只统计窗口内成交
        filtered = crud.get_pnl_distribution(db_session, worker_id, start_time=now - timedelta(days=5))
        assert sum(filtered["counts"]) == 1
        assert filtered["mean"] == 50.0


class TestTradeHistoryChart:
    """交易历史图表数据测试"""

    def test_get_trade_history_chart_empty(self, db_session):
        """无交易记录 → 铺满窗口的轴 + 全零曲线（轴仍随窗口切换，缺数据补 0）"""
        result = crud.get_trade_history_chart(db_session, 1, days=30)
        assert len(result["dates"]) == 31
        assert result["cumulative_pnl"] == [0.0] * 31
        assert result["trade_count"] == [0] * 31

    def test_get_trade_history_chart_basic(self, db_session):
        """基础历史数据"""
        worker_id = 1
        now = datetime.now()

        day1 = now - timedelta(days=2)
        t1 = WorkerTrade(
            worker_id=worker_id,
            trade_id="t1",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=50000,
            amount=50000,
            realized_pnl=100.0,
        )
        t1.created_at = day1
        db_session.add(t1)

        day2 = now - timedelta(days=1)
        t2 = WorkerTrade(
            worker_id=worker_id,
            trade_id="t2",
            symbol="BTCUSDT",
            side="sell",
            order_type="market",
            quantity=1,
            price=51000,
            amount=51000,
            realized_pnl=-50.0,
        )
        t2.created_at = day2
        db_session.add(t2)

        t3 = WorkerTrade(
            worker_id=worker_id,
            trade_id="t3",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=50000,
            amount=50000,
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

    def _add_trade(self, db_session, trade_id: str, realized_pnl: float, created_at: datetime) -> None:
        obj = WorkerTrade(
            worker_id=1,
            trade_id=trade_id,
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=50000,
            amount=50000,
            realized_pnl=realized_pnl,
            # created_at 显式传值：模型 default(func.now()) 仅在未提供时生效
            created_at=created_at,
        )
        db_session.add(obj)
        db_session.commit()

    def test_chart_pads_empty_days_with_zero(self, db_session):
        """X 轴必须铺满窗口：无成交的日期 daily=0，累计曲线保持前值（不归零、不留空）"""
        now = datetime.now()
        self._add_trade(db_session, "pad1", 100.0, now - timedelta(days=3))

        result = crud.get_trade_history_chart(db_session, 1, days=7)
        # 7 天窗口 → 铺满 8 个日桶（窗口起点当天 ~ 今天）
        assert len(result["dates"]) == 8
        assert len(result["cumulative_pnl"]) == 8
        # 无交易日 daily 与 count 补 0
        zero_idx = result["trade_count"].index(0)
        assert result["daily_pnl"][zero_idx] == 0.0
        # 累计曲线 carry-forward：全程非降（无负收益时），终点 == 总盈亏
        ladder = result["cumulative_pnl"]
        assert all(ladder[i] <= ladder[i + 1] for i in range(len(ladder) - 1))
        assert ladder[-1] == 100.0

    def test_chart_24h_uses_hourly_buckets(self, db_session):
        """24h 档按小时铺 24 个点（天粒度一天只有一个点，看不出走势）"""
        # 成交时间锚定在当前小时桶内（整点+15min）：now-30min 在半点前运行会
        # 落入上一个小时桶，trade_count[-1] 断言随墙钟波动
        trade_at = datetime.now().replace(minute=15, second=0, microsecond=0)
        self._add_trade(db_session, "h1", 60.0, trade_at)

        result = crud.get_trade_history_chart(db_session, 1, days=1)
        assert len(result["dates"]) == 24
        assert ":" in result["dates"][-1]  # 小时标签形如 11-16 15:00
        assert result["cumulative_pnl"][-1] == 60.0
        assert result["trade_count"] == [0] * 23 + [1]

    def test_chart_all_window_starts_from_first_trade(self, db_session):
        """all 档（days>365）起点收敛到首笔成交，不铺上万个空点；无成交返回空图"""
        now = datetime.now()
        self._add_trade(db_session, "a1", 20.0, now - timedelta(days=10))

        result = crud.get_trade_history_chart(db_session, 1, days=36500)
        # 首笔 10 天前 → 约 11 个日桶，绝不可能是 36500
        assert 10 <= len(result["dates"]) <= 12
        assert result["cumulative_pnl"][-1] == 20.0

        # 完全无成交的 worker → 空图
        empty = crud.get_trade_history_chart(db_session, 999, days=36500)
        assert empty["dates"] == []

    def test_window_to_days_all_covers_full_history(self, db_session):
        """all 档映射天数必须远超常规生命周期，否则「全部」曲线会被静默截断"""
        from worker.stats_service import _window_to_days

        assert _window_to_days("all") >= 3650


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
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p1",
                symbol="BTCUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=1000.0,
                margin_used=5000.0,
                status="OPEN",
            )
        )
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="p2",
                symbol="ETHUSDT",
                position_side="short",
                quantity=5.0,
                entry_price=3000.0,
                current_price=2950.0,
                unrealized_pnl=250.0,
                margin_used=7500.0,
                status="OPEN",
            )
        )
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_position_summary(worker_id)
        assert result["total_positions"] == 2
        assert result["long_positions"] == 1
        assert result["short_positions"] == 1
        assert result["total_value"] == pytest.approx(1.0 * 51000 + 5.0 * 2950, 0.01)
        assert result["total_unrealized_pnl"] == 1250.0
        assert result["total_margin_used"] == 12500.0
        assert len(result["positions"]) == 2

    def test_get_trading_summary_via_service(self, db_session):
        """通过service获取交易汇总"""
        from worker.stats_service import TradingStatsService

        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=100.0,
            )
        )
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_trading_summary(worker_id)
        assert result["total_trades"] == 1
        assert result["winning_trades"] == 1

    def test_get_pnl_distribution_via_service(self, db_session):
        """通过service获取盈亏分布"""
        from worker.stats_service import TradingStatsService

        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=100.0,
            )
        )
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_pnl_distribution(worker_id)
        assert result["mean"] != 0.0

    def test_get_trade_history_chart_via_service(self, db_session):
        """通过service获取交易历史图表"""
        from worker.stats_service import TradingStatsService

        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="t1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
                realized_pnl=100.0,
            )
        )
        db_session.commit()

        service = TradingStatsService(db_session)
        result = service.get_trade_history_chart(worker_id)
        assert len(result["dates"]) >= 0


class TestDataIntegrity:
    """数据完整性测试"""

    def test_trade_id_uniqueness(self, db_session):
        """交易ID唯一性"""
        worker_id = 1
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id="unique-1",
                symbol="BTCUSDT",
                side="buy",
                order_type="market",
                quantity=1,
                price=50000,
                amount=50000,
            )
        )
        db_session.commit()

        duplicate = WorkerTrade(
            worker_id=worker_id,
            trade_id="unique-1",
            symbol="ETHUSDT",
            side="buy",
            order_type="market",
            quantity=1,
            price=3000,
            amount=3000,
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_order_client_order_id_uniqueness(self, db_session):
        """订单client_order_id唯一性"""
        worker_id = 1
        db_session.add(
            WorkerOrder(
                worker_id=worker_id,
                client_order_id="order-1",
                symbol="BTCUSDT",
                side="buy",
                order_type="MARKET",
                quantity=1,
                status="FILLED",
            )
        )
        db_session.commit()

        duplicate = WorkerOrder(
            worker_id=worker_id,
            client_order_id="order-1",
            symbol="ETHUSDT",
            side="buy",
            order_type="MARKET",
            quantity=1,
            status="FILLED",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_position_position_id_uniqueness(self, db_session):
        """持仓position_id唯一性"""
        worker_id = 1
        db_session.add(
            WorkerPosition(
                worker_id=worker_id,
                position_id="pos-1",
                symbol="BTCUSDT",
                position_side="long",
                quantity=1.0,
                entry_price=50000.0,
                status="OPEN",
            )
        )
        db_session.commit()

        duplicate = WorkerPosition(
            worker_id=worker_id,
            position_id="pos-1",
            symbol="ETHUSDT",
            position_side="long",
            quantity=1.0,
            entry_price=3000.0,
            status="OPEN",
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestDerivePositionsFromTrades:
    """从未配对 fill 推导当前持仓（paper 账 worker_positions 表恒空的回退口径）"""

    @staticmethod
    def _add_fill(db_session, worker_id, trade_id, symbol, side, qty, price, pnl=None, ts=None, round_trip_id=None):
        db_session.add(
            WorkerTrade(
                worker_id=worker_id,
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                order_type="market",
                quantity=qty,
                price=price,
                amount=qty * price,
                realized_pnl=pnl,
                round_trip_id=round_trip_id,
                entry_time=ts,
            )
        )

    def test_net_long_entry_avg_and_unrealized(self, db_session):
        """buy 1@100 + buy 2@110 + sell 1@105（部分平仓未配对）→ 净 2 多头，均价同向加权"""
        worker_id = 1
        base = datetime(2026, 10, 28, 10, 0, 0)
        self._add_fill(db_session, worker_id, "f1", "BTC/USDT", "buy", 1.0, 100.0, ts=base)
        self._add_fill(db_session, worker_id, "f2", "BTC/USDT", "buy", 2.0, 110.0, ts=base + timedelta(minutes=5))
        self._add_fill(db_session, worker_id, "f3", "BTC/USDT", "sell", 1.0, 105.0, ts=base + timedelta(minutes=10))
        db_session.commit()

        items = crud.derive_positions_from_trades(db_session, worker_id)
        assert len(items) == 1
        pos = items[0]
        assert pos["symbol"] == "BTC/USDT"
        assert pos["side"] == "long"
        assert pos["quantity"] == 2.0
        # 开仓均价只取与净仓同向（buy）的 fill：(1*100 + 2*110) / 3
        assert pos["entry_price"] == pytest.approx(106.6666667, rel=1e-6)
        # 近似市价 = 最后一笔未配对 fill 的成交价（部分平仓的 105）
        assert pos["current_price"] == 105.0
        assert pos["unrealized_pnl"] == pytest.approx((105.0 - 320.0 / 3) * 2.0, rel=1e-6)
        assert pos["status"] == "OPEN"

    def test_net_short(self, db_session):
        """纯 sell fill → 空头持仓，side 短格式与 to_dict 契约一致"""
        worker_id = 1
        base = datetime(2026, 10, 28, 10, 0, 0)
        self._add_fill(db_session, worker_id, "s1", "ETH/USDT", "sell", 1.0, 200.0, ts=base)
        db_session.commit()

        items = crud.derive_positions_from_trades(db_session, worker_id)
        assert len(items) == 1
        assert items[0]["side"] == "short"
        assert items[0]["quantity"] == 1.0
        assert items[0]["entry_price"] == 200.0
        assert items[0]["position_id"] == "derived:1:ETH/USDT"

    def test_excludes_paired_rows(self, db_session):
        """已配对行（round_trip_id 组键回填）是历史 round-trip，不计入当前持仓"""
        worker_id = 1
        rt = "rt:1:f9"
        self._add_fill(db_session, worker_id, "old1", "BTC/USDT", "buy", 1.0, 100.0, pnl=5.0, round_trip_id=rt)
        self._add_fill(db_session, worker_id, "old2", "BTC/USDT", "sell", 1.0, 105.0, pnl=5.0, round_trip_id=rt)
        db_session.commit()

        assert crud.derive_positions_from_trades(db_session, worker_id) == []

    def test_live_fill_with_zero_pnl_included(self, db_session):
        """live 账口径：开仓 fill 的 realized_pnl 为 0.0（币安 realizedPnl="0" 误标）
        也无组键，必须参与净额推导——realized_pnl 过滤会让 live 持仓恒空"""
        worker_id = 3
        self._add_fill(db_session, worker_id, "l1", "ETH/USDT", "buy", 0.5, 3000.0, pnl=0.0)
        self._add_fill(db_session, worker_id, "l2", "ETH/USDT", "sell", 0.2, 3100.0, pnl=0.0)
        db_session.commit()

        items = crud.derive_positions_from_trades(db_session, worker_id)
        assert len(items) == 1
        assert items[0]["symbol"] == "ETH/USDT"
        assert items[0]["side"] == "long"
        assert items[0]["quantity"] == pytest.approx(0.3)
        assert items[0]["entry_price"] == pytest.approx(3000.0)

    def test_net_zero_symbol_skipped(self, db_session):
        """未配对但净额归零（对冲抵消）的 symbol 不出持仓行"""
        worker_id = 1
        self._add_fill(db_session, worker_id, "a1", "BTC/USDT", "buy", 1.0, 100.0)
        self._add_fill(db_session, worker_id, "a2", "BTC/USDT", "sell", 1.0, 100.0)
        self._add_fill(db_session, worker_id, "b1", "ETH/USDT", "buy", 3.0, 50.0)
        db_session.commit()

        items = crud.derive_positions_from_trades(db_session, worker_id)
        assert len(items) == 1
        assert items[0]["symbol"] == "ETH/USDT"
        assert items[0]["quantity"] == 3.0

    def test_fields_match_worker_position_to_dict(self, db_session):
        """推导行字段形状与 WorkerPosition.to_dict() 完全对齐"""
        worker_id = 1
        self._add_fill(db_session, worker_id, "x1", "BTC/USDT", "buy", 1.0, 100.0)
        db_session.commit()

        derived = crud.derive_positions_from_trades(db_session, worker_id)[0]

        expected = WorkerPosition(
            worker_id=worker_id,
            position_id="p",
            symbol="BTC/USDT",
            position_side="long",
            quantity=1.0,
            entry_price=100.0,
            # 列 default=0.0 只在 flush 时填充；内存对象必须显式给值才能调 to_dict
            unrealized_pnl=0.0,
            status="OPEN",
        ).to_dict()
        # to_dict 已双送 canonical 主键 position_side 与 deprecated 别名 side，
        # 与派生行（同样双送）的形状全等即视为契约对齐
        assert set(derived.keys()) == set(expected.keys())


class TestDerivePositionsDirectionVocab:
    """P0 防回归（设计 §4.5）：大写 side 混入不得反转净额方向/漏算持仓。

    改造前净额计算用 `r.side == "buy"` 全等匹配，DB 里的 "BUY" 行会被当作
    卖出计入净额并反向进出 same_dir，直接倒置持仓方向——本用例改造前必红。
    """

    def test_uppercase_side_no_flip(self, db_session) -> None:
        worker_id = 1
        crud.create_trade_if_not_exists(
            db_session,
            {
                "worker_id": worker_id,
                "trade_id": "vocab:case:1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "MARKET",
                "quantity": 1.0,
                "price": 100.0,
                # WorkerTrade.amount 列非空且无默认值，最小键集合按模型约束补齐
                "amount": 100.0,
                "entry_time": datetime(2026, 11, 1, 10, 0),
            },
        )
        # 同向第二笔写入大写（模拟 adapter 边界脏数据）
        crud.create_trade_if_not_exists(
            db_session,
            {
                "worker_id": worker_id,
                "trade_id": "vocab:case:2",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 1.0,
                "price": 110.0,
                "amount": 110.0,
                "entry_time": datetime(2026, 11, 1, 11, 0),
            },
        )
        positions = crud.derive_positions_from_trades(db_session, worker_id)
        # 两笔同向买入 → 净多头；反转 bug 下会是空头或漏笔
        assert len(positions) == 1
        assert positions[0]["position_side"] == "long"
        assert positions[0]["quantity"] == 2.0
