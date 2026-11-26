"""PaperTradeSync 最小自检：fill 字段映射 + 游标推进/幂等落库 + 持仓对账（sqlite 内存 DB）。"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# strategies 表要先进 metadata：workers.strategy_id 外键指向它，create_all 才能建表
import strategy.models
import worker.paper_trade_sync as pts
from collector.db.database import Base
from worker.models import WorkerOrder, WorkerPosition, WorkerTrade
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

    def __init__(
        self,
        batches: list[list[dict]],
        trade_batches: list[list[dict]] | None = None,
        snapshot_positions: list[dict] | None = None,
    ):
        self.batches = batches  # batches[i] = 第 i 轮新产生（非累积）
        self.trade_batches = trade_batches or []
        # snapshot_positions[i] = 第 i 轮引擎内存净仓（P1-10 持仓对账数据源）；
        # 未提供时视为引擎 snapshot 无 positions 键（与旧内核版本行为对齐）
        self.snapshot_positions = snapshot_positions
        self.stage = -1

    def advance(self):
        self.stage += 1

    def fills_since(self, cursor: int) -> list[dict]:
        full = [f for b in self.batches[: self.stage + 1] for f in b]
        return full[cursor:]

    def trades_since(self, cursor: int) -> list[dict]:
        full = [t for b in self.trade_batches[: self.stage + 1] for t in b]
        return full[cursor:]

    def snapshot(self) -> dict:
        positions = self.snapshot_positions[self.stage] if self.snapshot_positions else {}
        return {"equity": 0.0, "positions": positions}


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
    assert d["fill_id"] == f"paper:7:0:{NS}"
    assert d["symbol"] == "BTC/USDT"
    assert d["side"] == "buy"  # 引擎 "Buy" → ccxt 小写
    assert d["order_type"] == "MARKET"
    assert d["quantity"] == 30.0
    assert d["price"] == 100.05
    assert d["notional"] == 30.0 * 100.05
    assert d["fee"] == 0.0
    assert d["realized_pnl"] is None
    assert d["entry_time"] == datetime.fromtimestamp(NS / 1e9)
    # 新契约键：paper 单向净仓声明值固定 both（不从 side 推导）、reduce_only 恒 False
    assert d["position_side"] == "both"
    assert d["reduce_only"] is False


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
        rows = db.scalars(select(WorkerTrade).order_by(WorkerTrade.fill_id)).all()
    assert [r.fill_id for r in rows] == [
        f"paper:7:0:{NS}",
        f"paper:7:1:{NS + 60_000_000_000}",
    ]
    assert [r.side for r in rows] == ["buy", "sell"]


def test_fill_id_idempotent_across_run_replay(db_session_factory):
    """paper 重启清零重放同根 bar：fill_id 局部查重命中，不重复插入。"""
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
        rows = {r.fill_id.split(":")[2]: r for r in db.scalars(select(WorkerTrade)).all()}
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
        rows = db.scalars(select(WorkerTrade).order_by(WorkerTrade.fill_id)).all()
    assert len(rows) == 2
    assert {r.realized_pnl for r in rows} == {None, 148.5}


def test_backfill_writes_round_trip_id_to_all_rows(db_session_factory):
    """FLAT_TO_FLAT 分批平仓：entry 行 + 部分平仓行 + finalize 行写入同一组键。

    组键以 finalize fill id（exit_fill_ids 最大者）定位：rt:{worker_id}:{finalize_id}。
    """
    sync = PaperTradeSync(7)
    exit_ts = NS + 180_000_000_000
    driver = FakeDriver(
        batches=[
            [_fill(0, NS)],  # 开仓
            [_fill(1, NS + 60_000_000_000, "Sell")],  # 部分平仓
            [_fill(2, NS + 120_000_000_000, "Sell")],  # 最终平仓（finalize）
        ],
        trade_batches=[[], [], [_trade([1, 2], exit_ts)]],
    )
    for _ in range(3):
        driver.advance()
        sync.sync_once(driver)

    with db_session_factory() as db:
        rows = {r.fill_id.split(":")[2]: r for r in db.scalars(select(WorkerTrade)).all()}
    assert set(rows) == {"0", "1", "2"}
    # finalize_id = max([1, 2]) = 2 → 组键 rt:7:2
    assert {r.round_trip_id for r in rows.values()} == {"rt:7:2"}
    # 盈亏仍只回填 finalize 行；部分平仓行 realized_pnl 保持 None
    assert rows["1"].realized_pnl is None
    assert rows["2"].realized_pnl == pytest.approx(148.5)


def test_round_trip_id_idempotent_across_replay(db_session_factory):
    """paper 重启重演出同一配对：realized_pnl 已非空即跳过，组键不被重写。"""
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

    replay = PaperTradeSync(7)
    assert replay.sync_once(driver) == 0

    with db_session_factory() as db:
        rows = {r.fill_id.split(":")[2]: r for r in db.scalars(select(WorkerTrade)).all()}
    assert {r.round_trip_id for r in rows.values()} == {"rt:7:1"}
    assert len(rows) == 2


def test_fill_persists_order_filled_rows(db_session_factory):
    """每笔新落库 fill 同步落 FILLED 订单行（client_order_id 由 taker_order_id 派生）。"""
    sync = PaperTradeSync(7)
    driver = FakeDriver([[_fill(0, NS)], [_fill(1, NS + 60_000_000_000, "Sell")]])
    driver.advance()
    sync.sync_once(driver)
    driver.advance()
    sync.sync_once(driver)

    with db_session_factory() as db:
        orders = db.scalars(select(WorkerOrder).order_by(WorkerOrder.client_order_id)).all()
    assert [o.client_order_id for o in orders] == ["paper:7:t0", "paper:7:t1"]
    assert {o.status for o in orders} == {"FILLED"}
    entry = orders[0]
    # 落库方向词汇统一为 canonical 小写（上游原词大小写由 crud 归一）
    assert entry.side == "buy"
    assert entry.symbol == "BTC/USDT"
    assert entry.order_type == "MARKET"
    assert entry.filled_quantity == pytest.approx(30.0)
    assert entry.avg_fill_price == pytest.approx(100.05)


def test_same_order_partial_fills_accumulate(db_session_factory):
    """同一 taker_order_id 的分笔成交：单订单行，filled_quantity 累加、均价数量加权。"""
    f2 = _fill(1, NS + 1_000_000_000)
    f2["taker_order_id"] = "t0"  # 与 fill 0 同单
    f2["price"] = 101.05
    sync = PaperTradeSync(7)
    driver = FakeDriver([[_fill(0, NS), f2]])
    driver.advance()
    sync.sync_once(driver)

    with db_session_factory() as db:
        orders = db.scalars(select(WorkerOrder)).all()
    assert len(orders) == 1
    order = orders[0]
    assert order.client_order_id == "paper:7:t0"
    assert order.filled_quantity == pytest.approx(60.0)
    assert order.avg_fill_price == pytest.approx((100.05 * 30.0 + 101.05 * 30.0) / 60.0)


def test_order_upsert_idempotent_across_replay(db_session_factory):
    """paper 重启重放同批 fill：查重命中走 exists 分支，订单行不重复累加。"""
    sync = PaperTradeSync(7)
    driver = FakeDriver([[_fill(0, NS)]])
    driver.advance()
    sync.sync_once(driver)

    replay = PaperTradeSync(7)
    assert replay.sync_once(driver) == 0

    with db_session_factory() as db:
        orders = db.scalars(select(WorkerOrder)).all()
    assert len(orders) == 1
    assert orders[0].filled_quantity == pytest.approx(30.0)


# ── P1-10 持仓对账落库 ──────────────────────────────────────────


def test_positions_upserted_from_snapshot(db_session_factory):
    """引擎 snapshot 净仓对账落 worker_positions：方向/数量以引擎为准，明细复用 derive。"""
    sync = PaperTradeSync(7)
    driver = FakeDriver([[_fill(0, NS)]], snapshot_positions=[{"BTC/USDT": 30.0}])
    driver.advance()
    sync.sync_once(driver)

    with db_session_factory() as db:
        rows = db.scalars(select(WorkerPosition)).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.position_id == "paper:7:BTC/USDT"
    assert row.symbol == "BTC/USDT"
    assert row.position_side == "long"
    assert row.quantity == pytest.approx(30.0)
    # entry/current 复用未配对 fill 推导（同 derive 算法，不另立口径）
    assert row.entry_price == pytest.approx(100.05)
    assert row.current_price == pytest.approx(100.05)
    assert row.status == "OPEN"
    assert row.opened_at is not None


def test_positions_unchanged_skips_rewrite(db_session_factory):
    """连续两轮同持仓：第二轮对账无写库（dirty 未触发，updated_at 不刷新）。"""
    from worker import crud

    sync = PaperTradeSync(7)
    driver = FakeDriver([[_fill(0, NS)]], snapshot_positions=[{"BTC/USDT": 30.0}])
    driver.advance()
    sync.sync_once(driver)

    with db_session_factory() as db:
        before = db.scalars(select(WorkerPosition)).one().updated_at

    assert sync._sync_positions(driver, crud) == 0

    with db_session_factory() as db:
        after = db.scalars(select(WorkerPosition)).one().updated_at
    assert before == after


def test_positions_closed_when_engine_flat(db_session_factory):
    """引擎净仓归零：OPEN 行标 CLOSED 留痕（quantity 清零、closed_at 落时刻）。"""
    sync = PaperTradeSync(7)
    driver = FakeDriver(
        batches=[[_fill(0, NS)], [_fill(1, NS + 60_000_000_000, "Sell")]],
        snapshot_positions=[{"BTC/USDT": 30.0}, {}],
    )
    for _ in range(2):
        driver.advance()
        sync.sync_once(driver)

    with db_session_factory() as db:
        row = db.scalars(select(WorkerPosition)).one()
    assert row.status == "CLOSED"
    assert row.quantity == pytest.approx(0.0)
    assert row.closed_at is not None


def test_positions_row_reused_across_run_replay(db_session_factory):
    """paper 重启重演：position_id 稳定，CLOSED→OPEN 复用同一行不重复建。"""
    sync = PaperTradeSync(7)
    driver = FakeDriver(
        batches=[[_fill(0, NS)], [_fill(1, NS + 60_000_000_000, "Sell")]],
        snapshot_positions=[{"BTC/USDT": 30.0}, {}],
    )
    for _ in range(2):
        driver.advance()
        sync.sync_once(driver)

    # 重启：的重同步器从头重演，引擎重新建仓
    replay = PaperTradeSync(7)
    replay_driver = FakeDriver([[_fill(0, NS)]], snapshot_positions=[{"BTC/USDT": 30.0}])
    replay_driver.advance()
    replay.sync_once(replay_driver)

    with db_session_factory() as db:
        rows = db.scalars(select(WorkerPosition)).all()
    assert len(rows) == 1
    assert rows[0].position_id == "paper:7:BTC/USDT"
    assert rows[0].status == "OPEN"
    assert rows[0].quantity == pytest.approx(30.0)


def test_positions_entry_fallback_when_derive_missing(db_session_factory):
    """反手后 derive 缺行（fill 已配对被排除）：entry 退回最后一笔 fill 成交价。"""
    exit_ts = NS + 60_000_000_000
    sync = PaperTradeSync(7)
    # fill 已全部配对（round_trip_id 回填）→ derive 无行；引擎 net 持仓仍 30（模拟反手）
    driver = FakeDriver(
        batches=[[_fill(0, NS)]],
        trade_batches=[[_trade([0], exit_ts)]],
        snapshot_positions=[{"BTC/USDT": 30.0}],
    )
    driver.advance()
    sync.sync_once(driver)

    with db_session_factory() as db:
        row = db.scalars(select(WorkerPosition)).one()
    assert row.quantity == pytest.approx(30.0)
    assert row.entry_price == pytest.approx(100.05)  # 来自最后 fill 价 fallback
    assert row.entry_price > 0
    assert row.status == "OPEN"


def test_positions_snapshot_without_fills(db_session_factory):
    """引擎有仓但 fill 未落库（游标时差）：对账不炸，产出 entry=0 的 OPEN 行。"""
    from worker import crud

    sync = PaperTradeSync(7)
    driver = FakeDriver(batches=[[]], snapshot_positions=[{"ETH/USDT": 5.0}])
    driver.advance()
    assert sync._sync_positions(driver, crud) == 1

    with db_session_factory() as db:
        row = db.scalars(select(WorkerPosition)).one()
    assert row.symbol == "ETH/USDT"
    assert row.position_side == "long"
    assert row.quantity == pytest.approx(5.0)
    assert row.entry_price == pytest.approx(0.0)
