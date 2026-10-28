"""PaperTradeSync 最小自检：fill 字段映射 + 游标推进/幂等落库（sqlite 内存 DB）。"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# strategies 表要先进 metadata：workers.strategy_id 外键指向它，create_all 才能建表
import strategy.models
import worker.paper_trade_sync as pts
from collector.db.database import Base
from worker.models import WorkerTrade
from worker.paper_trade_sync import PaperTradeSync

NS = 1_700_000_000_000_000_000


def _fill(fill_id: int, ts: int, side: str = "Buy") -> dict:
    return {
        "timestamp_ns": ts,
        "instrument": ("spot", "BTC", "USDT"),
        "taker_order_id": f"t{fill_id}",
        "maker_order_id": "",
        "taker_side": side,
        "price": 100.05,
        "quantity": 30.0,
        "fill_id": fill_id,
    }


def _trade(exit_fill_ids: list[int], ts: int) -> dict:
    """配对 round-trip（PaperDriver.trades_since 契约，价格字段已是 f64 口径）。"""
    return {
        "timestamp_ns": ts,
        "price": 105.0,
        "quantity": 30.0,
        "buyer_order_id": "t0",
        "seller_order_id": "t1",
        "realized_pnl": 148.5,
        "commission": 1.50,
        "net_quantity": 30.0,
        "entry_price": 100.05,
        "entry_time_ns": NS,
        "instrument": ("spot", "BTC", "USDT"),
        "entry_fill_ids": [0],
        "exit_fill_ids": exit_fill_ids,
    }


class FakeDriver:
    """按阶段解锁的 append-only fills_since / trades_since 假驱动（模拟 paper 内核产出）。"""

    def __init__(self, batches: list[list[dict]], trade_batches: list[list[dict]] | None = None):
        self.batches = batches  # batches[i] = 第 i 轮新产生（非累积）
        self.trade_batches = trade_batches or []
        self.stage = -1

    def advance(self):
        self.stage += 1

    def fills_since(self, cursor: int) -> list[dict]:
        full = [f for b in self.batches[: self.stage + 1] for f in b]
        return full[cursor:]

    def trades_since(self, cursor: int) -> list[dict]:
        full = [t for b in self.trade_batches[: self.stage + 1] for t in b]
        return full[cursor:]


@pytest.fixture()
def db_session_factory(monkeypatch):
    """sqlite 内存库接管 PaperTradeSync 的 get_db_session，返回 (Session, 表查询助手)。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pts, "get_db_session", factory)
    return factory


def test_to_trade_data_spot():
    d = PaperTradeSync(7)._to_trade_data(_fill(0, NS))
    assert d["worker_id"] == 7
    assert d["trade_id"] == f"paper:7:0:{NS}"
    assert d["symbol"] == "BTC/USDT"
    assert d["side"] == "buy"  # 引擎 "Buy" → ccxt 小写
    assert d["order_type"] == "MARKET"
    assert d["quantity"] == 30.0
    assert d["price"] == 100.05
    assert d["amount"] == 30.0 * 100.05
    assert d["fee"] == 0.0
    assert d["realized_pnl"] is None
    assert d["entry_time"] == datetime.fromtimestamp(NS / 1e9)


def test_to_trade_data_swap_instrument():
    fill = _fill(1, NS)
    fill["instrument"] = ("swap", "ETH", "USDT", "usd_margin", 0.01)
    d = PaperTradeSync(7)._to_trade_data(fill)
    assert d["symbol"] == "ETH/USDT"


def test_sync_once_cursor_and_idempotency(db_session_factory):
    sync = PaperTradeSync(7)
    driver = FakeDriver([[_fill(0, NS)], [_fill(1, NS + 60_000_000_000, "Sell")]])
    driver.advance()

    # 第一轮：游标 0 拉到 1 笔并落库
    assert sync.sync_once(driver) == 1
    assert sync._cursor == 1

    driver.advance()

    # 第二轮：只增量拉到新 fill，已入库的重复 fill 由游标截断不会重插
    assert sync.sync_once(driver) == 1
    assert sync._cursor == 2

    # 第三轮：无新增
    assert sync.sync_once(driver) == 0

    with db_session_factory() as db:
        rows = db.scalars(select(WorkerTrade).order_by(WorkerTrade.trade_id)).all()
    assert [r.trade_id for r in rows] == [
        f"paper:7:0:{NS}",
        f"paper:7:1:{NS + 60_000_000_000}",
    ]
    assert [r.side for r in rows] == ["buy", "sell"]


def test_trade_id_idempotent_across_run_replay(db_session_factory):
    """paper 重启清零重放同根 bar：trade_id 局部查重命中，不重复插入。"""
    sync = PaperTradeSync(7)
    driver = FakeDriver([[_fill(0, NS)]])
    driver.advance()
    sync.sync_once(driver)

    # 模拟重启：新同步器游标归零、同 fill_id 同 bar 重演
    replay = PaperTradeSync(7)
    assert replay.sync_once(driver) == 0

    with db_session_factory() as db:
        assert len(db.scalars(select(WorkerTrade)).all()) == 1


def test_backfill_paired_pnl_to_finalize_fill(db_session_factory):
    """配对毛盈亏只回填 finalize fill（exit_fill_ids 最大者）行，entry 行保持 None。"""
    sync = PaperTradeSync(7)
    exit_ts = NS + 120_000_000_000
    driver = FakeDriver(
        batches=[[_fill(0, NS)], [_fill(1, NS + 60_000_000_000, "Sell")]],
        trade_batches=[[], [_trade([1], exit_ts)]],
    )
    driver.advance()
    sync.sync_once(driver)
    driver.advance()
    sync.sync_once(driver)

    assert sync._trades_cursor == 1
    with db_session_factory() as db:
        rows = {r.trade_id.split(":")[2]: r for r in db.scalars(select(WorkerTrade)).all()}
    assert rows["0"].realized_pnl is None  # entry fill 行不背盈亏
    fin = rows["1"]
    assert fin.realized_pnl == pytest.approx(148.5)
    assert fin.exit_time == datetime.fromtimestamp(exit_ts / 1e9)
    assert fin.realized_pnl_pct == pytest.approx(148.5 / (100.05 * 30.0) * 100)


def test_backfill_idempotent_across_run_replay(db_session_factory):
    """paper 重启重演出同一配对：realized_pnl 已非空即跳过，不重复回写。"""
    exit_ts = NS + 120_000_000_000
    driver = FakeDriver(
        batches=[[_fill(0, NS)], [_fill(1, NS + 60_000_000_000, "Sell")]],
        trade_batches=[[], [_trade([1], exit_ts)]],
    )
    sync = PaperTradeSync(7)
    driver.advance()
    sync.sync_once(driver)
    driver.advance()
    sync.sync_once(driver)

    # 模拟重启重放：游标与索引归零，fills 幂等命中、配对行已带盈亏被跳过
    # （跳过也消费游标，故 trades_cursor 推进到 1）
    replay = PaperTradeSync(7)
    assert replay.sync_once(driver) == 0
    assert replay._trades_cursor == 1

    with db_session_factory() as db:
        rows = db.scalars(select(WorkerTrade).order_by(WorkerTrade.trade_id)).all()
    assert len(rows) == 2
    assert {r.realized_pnl for r in rows} == {None, 148.5}
