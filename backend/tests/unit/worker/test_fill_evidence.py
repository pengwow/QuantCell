"""P0-01 成交证据链验收。

覆盖三件事：
1. crud.create_trade_if_not_exists 与 worker_fill_evidence 同事务双写，
   同 venue_trade_id 二次插入不再产生新行（两把查重锁并存）；
2. _to_trade_data 从 ccxt 回报 info 提取 clientOrderId / orderId（订单意图关联）；
3. find_orphan_fill_client_ids 能识别「有成交无订单」的 evidence 行（孤立成交观测）。
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# strategies 表要先进 metadata：workers.strategy_id 外键指向它，create_all 才能建表
import strategy.models
import worker.live_trade_sync as lts
from collector.db.database import Base
from worker import crud
from worker.models import WorkerFillEvidence, WorkerOrder, WorkerTrade


class _FakeCcxt:
    def milliseconds(self):
        return 1_700_000_000_000

    def fetch_my_trades(self, symbol, since=None):
        return []


class _FakeExchange:
    """构造参数照单全收，只暴露 .exchange，测试不触网"""

    def __init__(self, **kwargs):
        self.exchange = _FakeCcxt()


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    """sqlite 内存库 fixture（与 test_paper_trade_sync 同模式，落盘 tmp 便于失败排查）"""
    engine = create_engine(f"sqlite:///{tmp_path}/evidence.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(lts, "get_db_session", lambda: _Ctx(session))
    yield session
    session.close()


class _Ctx:
    """最小 contextmanager 复刻 get_db_session（不 commit，由 crud 自行提交）"""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.session.rollback()
        return False


def _trade_data(trade_id: str = "t1", client_order_id: str | None = "co1") -> dict:
    """live 链路的 trade_data 契约样本（字段与 live_trade_sync._to_trade_data 对齐）"""
    return {
        "worker_id": 1,
        "trade_id": trade_id,
        "symbol": "BTC/USDT",
        "side": "buy",
        "order_type": "MARKET",
        "quantity": 0.01,
        "price": 50000.0,
        "amount": 500.0,
        "fee": 0.35,
        "fee_currency": "USDT",
        "realized_pnl": None,
        "realized_pnl_pct": None,
        "entry_time": datetime.now(),
        "exit_time": None,
        "client_order_id": client_order_id,
        "venue_order_id": "vo-1",
        "raw_data": "{}",
    }


def _enable_evidence(monkeypatch, enabled: bool):
    """统一控制开关双入口：live_trade_sync 模块级 import 与 crud 函数内 import"""
    monkeypatch.setattr(lts, "get_flag", lambda key, default=True: enabled)
    monkeypatch.setattr("utils.config_manager.get_flag", lambda key, default=True: enabled)


def test_evidence_double_write_and_conflict(db_session, monkeypatch):
    """同 trade_id 二次插入：evidence 幂等命中，trade 不重复入账"""
    _enable_evidence(monkeypatch, True)

    first = crud.create_trade_if_not_exists(db_session, _trade_data("t1"))
    assert first is not None
    second = crud.create_trade_if_not_exists(db_session, _trade_data("t1"))

    assert second is None  # 幂等命中返回 None（未新建），由 trade_id 查重锁定
    assert db_session.query(WorkerTrade).count() == 1
    assert db_session.query(WorkerFillEvidence).count() == 1
    ev = db_session.query(WorkerFillEvidence).one()
    assert ev.venue_trade_id == "t1"
    assert ev.client_order_id == "co1"
    assert ev.source == "sync"


def test_evidence_disabled_falls_back_to_trade_id(db_session, monkeypatch):
    """开关关闭：不写 evidence，幂等完全退回 trade_id 查重（旧行为）"""
    _enable_evidence(monkeypatch, False)

    crud.create_trade_if_not_exists(db_session, _trade_data("t2"))
    crud.create_trade_if_not_exists(db_session, _trade_data("t2"))

    assert db_session.query(WorkerTrade).count() == 1
    assert db_session.query(WorkerFillEvidence).count() == 0


def test_no_client_order_id_skips_evidence(db_session, monkeypatch):
    """client_order_id 缺失（paper / journal 通道）：不写 evidence，trade 正常落库"""
    _enable_evidence(monkeypatch, True)

    crud.create_trade_if_not_exists(db_session, _trade_data("t3", client_order_id=None))

    assert db_session.query(WorkerTrade).count() == 1
    assert db_session.query(WorkerFillEvidence).count() == 0


def test_to_trade_data_extracts_order_ref(db_session, monkeypatch):
    """回报 info 提取：clientOrderId / orderId 缺失时落 None 不落空串"""
    # 构造 LiveTradeSync 会走 load_cursor / load_flags：挂 db_session 挡住真库，
    # 交易所门面换 fake 避免真构造 ccxt BinanceExchange
    _enable_evidence(monkeypatch, True)
    monkeypatch.setattr(lts, "BinanceExchange", _FakeExchange)
    sync = lts.LiveTradeSync(worker_id=1, api_key="k", api_secret="s", symbol="BTC/USDT")
    data = sync._to_trade_data(
        {
            "id": "v-1",
            "timestamp": 1_700_000_000_000,
            "amount": 0.02,
            "price": 51000.0,
            "side": "sell",
            "orderType": "limit",
            "fee": {"cost": 0.4, "currency": "USDT"},
            "info": {"clientOrderId": "web_xyz", "orderId": 9001, "realizedPnl": "12.5"},
        }
    )
    assert data["client_order_id"] == "web_xyz"
    assert data["venue_order_id"] == "9001"
    assert data["realized_pnl"] == 12.5

    data2 = sync._to_trade_data({"id": "v-2", "timestamp": None, "info": {}})
    assert data2["client_order_id"] is None
    assert data2["venue_order_id"] is None


def test_orphan_fill_detection(db_session, monkeypatch):
    """孤立成交：evidence 有 client_order_id 而订单表无此行 → 告警列表命中"""
    _enable_evidence(monkeypatch, True)

    def _ev(tid: str, cid: str, symbol: str = "BTC/USDT", qty: float = 0.01, side: str = "buy"):
        return WorkerFillEvidence(
            worker_id=1,
            client_order_id=cid,
            venue_order_id=f"vo-{tid}",
            venue_trade_id=tid,
            symbol=symbol,
            side=side,
            qty=qty,
            price=50000.0,
            fee=0.35,
            source="sync",
        )

    # 孤立成交（订单行不存在）+ 正常成交（订单行存在）
    db_session.add(_ev("t-orphan", "co-orphan"))
    db_session.add(_ev("t-normal", "co-normal", qty=0.02))
    db_session.add(
        WorkerOrder(
            id=1,
            worker_id=1,
            client_order_id="co-normal",
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.02,
            price=51000.0,
            status="filled",
        )
    )
    db_session.commit()

    orphans = lts.find_orphan_fill_client_ids(1)
    assert orphans == ["co-orphan"], "孤立成交应命中，正常成交(订单存在)不应命中"
