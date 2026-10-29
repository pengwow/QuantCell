"""crud.get_worker_trades_grouped 最小自检：组聚合 / unpaired / 过滤 / 组分页。"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# workers.strategy_id 外键指向 strategies，create_all 前需该表进 metadata
import strategy.models
from collector.db.database import Base
from worker import crud
from worker.models import WorkerTrade

WORKER_ID = 7


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _row(
    fill_id: int,
    ts: datetime,
    side: str,
    price: float,
    qty: float,
    round_trip_id: str | None = None,
    realized_pnl: float | None = None,
    exit_time: datetime | None = None,
    symbol: str = "BTC/USDT",
    created_at: datetime | None = None,
) -> WorkerTrade:
    """直插 WorkerTrade 行（绕过 sync），trade_id 沿用 paper 口径。"""
    return WorkerTrade(
        worker_id=WORKER_ID,
        trade_id=f"paper:{WORKER_ID}:{fill_id}:{int(ts.timestamp() * 1e9)}",
        symbol=symbol,
        side=side,
        order_type="MARKET",
        quantity=qty,
        price=price,
        amount=qty * price,
        fee=0.0,
        fee_currency="USDT",
        realized_pnl=realized_pnl,
        realized_pnl_pct=None,
        entry_time=ts,
        exit_time=exit_time,
        created_at=created_at or ts,
        round_trip_id=round_trip_id,
    )


def test_paired_group_merges_into_one_row(db):
    t0 = datetime(2026, 10, 20, 10, 0, 0)
    t1 = datetime(2026, 10, 20, 11, 0, 0)
    rt = f"rt:{WORKER_ID}:1"
    db.add_all(
        [
            _row(0, t0, "buy", 100.05, 30.0, round_trip_id=rt),
            _row(1, t1, "sell", 105.0, 30.0, round_trip_id=rt, realized_pnl=148.5, exit_time=t1),
        ]
    )
    db.commit()

    items, total = crud.get_worker_trades_grouped(db, WORKER_ID)
    assert total == 1
    it = items[0]
    assert it["trade_id"] == rt
    assert it["status"] == "closed"
    assert it["direction"] == "long"
    assert it["entry_side"] == "buy" and it["exit_side"] == "sell"
    assert it["entry_price"] == pytest.approx(100.05)  # 开仓 VWAP
    assert it["exit_price"] == pytest.approx(105.0)  # 平仓 VWAP
    assert it["size"] == pytest.approx(30.0)
    assert it["pnl"] == pytest.approx(148.5)  # 取 finalize 行
    assert it["return_pct"] == pytest.approx(148.5 / (100.05 * 30.0) * 100)
    assert [f["offset"] for f in it["fills"]] == ["open", "close"]
    assert it["entry_fill_ids"] == [it["fills"][0]["fill_id"]]
    assert it["exit_fill_ids"] == [it["fills"][1]["fill_id"]]


def test_unpaired_row_is_own_group(db):
    db.add(_row(0, datetime(2026, 10, 20, 10, 0, 0), "buy", 100.05, 30.0))
    db.commit()

    items, total = crud.get_worker_trades_grouped(db, WORKER_ID)
    assert total == 1
    it = items[0]
    assert it["status"] == "unpaired"
    assert it["direction"] is None
    assert it["pnl"] == 0.0  # realized_pnl 为 None 时记 0，防前端 toFixed 崩
    assert it["exit_time"] is None
    assert it["exit_price"] == pytest.approx(100.05)  # 无平仓行回退开仓价
    assert it["size"] == pytest.approx(30.0)
    assert len(it["fills"]) == 1


def test_symbol_direction_and_date_filters(db):
    rt_a = f"rt:{WORKER_ID}:1"
    rt_b = f"rt:{WORKER_ID}:3"
    db.add_all(
        [
            _row(0, datetime(2026, 10, 15, 9), "buy", 100.0, 1.0, round_trip_id=rt_a),
            _row(
                1,
                datetime(2026, 10, 15, 10),
                "sell",
                101.0,
                1.0,
                rt_a,
                1.0,
                datetime(2026, 10, 15, 10),
                created_at=datetime(2026, 10, 15, 10),
            ),
            _row(2, datetime(2026, 10, 16, 9), "sell", 2000.0, 1.0, rt_b, symbol="ETH/USDT"),
            _row(3, datetime(2026, 10, 16, 10), "buy", 1990.0, 1.0, rt_b, 10.0, datetime(2026, 10, 16, 10), "ETH/USDT"),
            _row(4, datetime(2026, 10, 17, 9), "buy", 100.0, 1.0),  # 无配对 BTC 行
        ]
    )
    db.commit()

    # 标的过滤在行级
    items, total = crud.get_worker_trades_grouped(db, WORKER_ID, symbol="ETH/USDT")
    assert total == 1 and items[0]["direction"] == "short"

    # 方向过滤在组级：unpaired 组 direction=None 自然被排除
    items, total = crud.get_worker_trades_grouped(db, WORKER_ID, direction="long")
    assert total == 1 and items[0]["symbol"] == "BTC/USDT"

    items, total = crud.get_worker_trades_grouped(db, WORKER_ID, start_time=datetime(2026, 10, 16, 0, 0, 0))
    assert total == 2  # 16 日 ETH 组 + 17 日 unpaired

    # end_time 为 00:00:00 时补到当日末：10/16 边界仍包含 16 日组
    items, total = crud.get_worker_trades_grouped(db, WORKER_ID, end_time=datetime(2026, 10, 16, 0, 0, 0))
    assert total == 2  # 15 日 BTC 组 + 16 日 ETH 组


def test_group_pagination_does_not_split_groups(db):
    for g in range(3):
        ts = datetime(2026, 10, 20 + g, 9)
        rt = f"rt:{WORKER_ID}:{g}"
        db.add_all(
            [
                _row(g * 2, ts, "buy", 100.0, 1.0, rt),
                _row(g * 2 + 1, ts, "sell", 101.0, 1.0, rt, 1.0, ts),
            ]
        )
    db.commit()

    items, total = crud.get_worker_trades_grouped(db, WORKER_ID, skip=0, limit=2)
    assert total == 3 and len(items) == 2
    assert all(len(it["fills"]) == 2 for it in items)  # 组不被切断
    assert items[0]["trade_id"] == f"rt:{WORKER_ID}:2"  # 组间按 MAX(created_at) 倒序
