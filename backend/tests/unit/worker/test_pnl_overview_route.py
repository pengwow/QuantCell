"""GET /api/v1/workers/stats/pnl-overview 的「今日 vs 昨日同期」口径测试。

首页 KPI2 的「较昨日同期」不是自然日对比：两个窗口都按滚动 hours 切片，
今日 [now-h, +∞)、昨日同期 [now-2h, now-h)，分子分母同源，只换时间边界。
这里直接调路由函数（与 test_worker_total_profit 同口径），用内存 SQLite 造数。
"""

import asyncio
from datetime import datetime, timedelta

import sqlalchemy as sa

import strategy.models  # 注册 strategies 表（workers.strategy_id 外键依赖）
import worker.models
from collector.db.database import Base
from worker import routes
from worker.models import Worker, WorkerCapital, WorkerTrade


def _make_db():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sa.orm.sessionmaker(bind=engine)()


def _worker(session, name: str = "w", config: str = "{}") -> Worker:
    worker = Worker(name=name, status="stopped", config=config)
    session.add(worker)
    session.commit()
    return worker


def _trade(session, worker_id: int, pnl: float, hours_ago: float, tag: str) -> WorkerTrade:
    """造一条 entry_time = now - hours_ago 的已配对成交。"""
    trade = WorkerTrade(
        worker_id=worker_id,
        fill_id=f"t-{tag}",
        symbol="BTC/USDT",
        side="sell",
        order_type="market",
        quantity=0.01,
        price=50000.0,
        notional=500.0,
        realized_pnl=pnl,
        entry_time=datetime.now() - timedelta(hours=hours_ago),
    )
    session.add(trade)
    session.commit()
    return trade


def _overview(session, hours: int = 24) -> dict:
    # current_user={} → 鉴权关闭路径，_worker_owner_filter 返回 None（不过滤归属）
    resp = asyncio.run(routes.get_pnl_overview(hours=hours, db=session, current_user={}))
    return resp.data


def test_prev_window_symmetry_and_fields():
    session = _make_db()
    worker = _worker(session)
    session.add(WorkerCapital(worker_id=worker.id, initial_capital=1000.0))
    session.commit()

    _trade(session, worker.id, 10.0, hours_ago=1, tag="today")  # 今日窗口
    _trade(session, worker.id, 5.0, hours_ago=30, tag="prev")  # 昨日同期窗口
    _trade(session, worker.id, 100.0, hours_ago=72, tag="older")  # 两个窗口都不含

    data = _overview(session, hours=24)
    assert data["realized_pnl"] == 10.0
    assert data["trade_count"] == 1
    assert data["prev_realized_pnl"] == 5.0
    assert data["prev_trade_count"] == 1
    # 同一分母（Σ initial_capital = 1000）→ 1.0% vs 0.5%
    assert data["pnl_pct"] == 1.0
    assert data["prev_pnl_pct"] == 0.5


def test_prev_window_excludes_trades_older_than_two_windows():
    session = _make_db()
    worker = _worker(session)
    session.add(WorkerCapital(worker_id=worker.id, initial_capital=1000.0))
    session.commit()

    _trade(session, worker.id, 7.0, hours_ago=49, tag="beyond-48h")  # 48h 之外，不进 prev
    _trade(session, worker.id, 3.0, hours_ago=47, tag="inside-48h")  # 48h 之内，进 prev

    data = _overview(session, hours=24)
    assert data["prev_realized_pnl"] == 3.0
    assert data["prev_trade_count"] == 1
    assert data["realized_pnl"] == 0.0
    assert data["trade_count"] == 0


def test_prev_pct_null_when_capital_zero():
    session = _make_db()
    worker = _worker(session)  # 无 WorkerCapital 行、config 无 initial_capital → 分母 0
    _trade(session, worker.id, 4.0, hours_ago=1, tag="today")
    _trade(session, worker.id, 2.0, hours_ago=30, tag="prev")

    data = _overview(session, hours=24)
    assert data["capital"] == 0.0
    assert data["pnl_pct"] is None
    assert data["prev_pnl_pct"] is None
    # 分子照实返回（算得出就给），只是不给百分比
    assert data["prev_realized_pnl"] == 2.0


def test_window_hours_moves_prev_window():
    """hours 参数前后两窗口一起移动（不是固定 24h 的自然日口径）。"""
    session = _make_db()
    worker = _worker(session)
    session.add(WorkerCapital(worker_id=worker.id, initial_capital=1000.0))
    session.commit()

    _trade(session, worker.id, 6.0, hours_ago=3, tag="recent")  # 6h 窗口内
    _trade(session, worker.id, 9.0, hours_ago=9, tag="prev-6h")  # prev = [12h, 6h)

    data = _overview(session, hours=6)
    assert data["realized_pnl"] == 6.0
    assert data["prev_realized_pnl"] == 9.0
