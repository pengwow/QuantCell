"""Worker.to_dict total_profit 口径一致性测试。

回归背景：原实现读取 worker_performances 表（全库无写入方、恒为空），
列表卡片总盈利恒为 0，与详情页 stats/overview（sum(realized_pnl)）不一致。
修复后必须等于成交明细已实现盈亏汇总。
"""

import sqlalchemy as sa

import strategy.models  # 注册 strategies 表（workers.strategy_id 外键依赖）
import worker.models  # 注册全部 worker ORM 模型到 Base.metadata
from collector.db.database import Base
from worker.models import Worker, WorkerTrade


def _make_db():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sa.orm.sessionmaker(bind=engine)()


def _trade(worker_id: int, pnl: float) -> WorkerTrade:
    """构造一条满足非空约束的成交记录。"""
    return WorkerTrade(
        worker_id=worker_id,
        trade_id=f"t-{worker_id}-{pnl}",
        symbol="BTC/USDT",
        side="buy",
        order_type="market",
        quantity=0.01,
        price=50000.0,
        amount=500.0,
        realized_pnl=pnl,
    )


def test_total_profit_matches_realized_pnl_sum():
    session = _make_db()
    worker = Worker(name="马丁", status="stopped")
    session.add(worker)
    session.commit()
    session.add_all(
        [
            _trade(worker.id, -20.0),
            _trade(worker.id, 5.0),
            _trade(worker.id, -6.06),
        ]
    )
    session.commit()

    data = worker.to_dict()
    # 与 stats/overview 的 net_profit（sum(realized_pnl)）同口径
    assert abs(data["total_profit"] - (-21.06)) < 1e-6


def test_total_profit_zero_when_no_trades():
    session = _make_db()
    worker = Worker(name="空任务", status="stopped")
    session.add(worker)
    session.commit()
    assert worker.to_dict()["total_profit"] == 0.0
