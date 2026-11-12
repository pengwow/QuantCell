"""P0-02 同步游标持久化验收。

覆盖：DB 游标读写 roundtrip、构造时读游标续拉、sync_once 同事务推进、
启动回补的告警/截断边界、开关关闭回退旧行为。
"""

from hashlib import sha1

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import worker.live_trade_sync as lts
from collector.db.database import Base
from worker.models import WorkerSyncCursor, WorkerTrade

NOW_MS = 1_700_000_000_000


class _FakeCcxt:
    def __init__(self):
        self._trades: list[dict] = []

    def milliseconds(self):
        return NOW_MS

    def fetch_my_trades(self, symbol, since=None):
        return self._trades


class _FakeExchange:
    """只需暴露 .exchange（ccxt 门面），构造参数照单全收"""

    def __init__(self, **kwargs):
        self.exchange = _FakeCcxt()


@pytest.fixture()
def engine_session(monkeypatch, tmp_path):
    """sqlite 内存库 + live_trade_sync 模块级 get_db_session 指向它"""
    from collector.db.database import _import_all_models

    _import_all_models()  # workers 表外键依赖 strategies 表，必须先注册全模型
    engine = create_engine(f"sqlite:///{tmp_path}/cursor.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    instances = {"session": session}
    monkeypatch.setattr(lts, "get_db_session", lambda: _Ctx(session))
    yield instances
    session.close()


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.session.rollback()
        return False


def _patch_flags(monkeypatch, cursor_enabled: bool = True):
    flag_map = {"worker.execution.sync_cursor_enabled": cursor_enabled}
    getter = lambda key, default=True: flag_map.get(key, default)  # noqa: E731
    monkeypatch.setattr(lts, "get_flag", getter)
    # crud.create_trade_if_not_exists 内部 import 真实 get_flag：走 config.toml
    # 的 fill_evidence_enabled（默认 true），无 client_order_id 时本就不写 evidence


def _make_sync(worker_id: int = 1) -> lts.LiveTradeSync:
    return lts.LiveTradeSync(worker_id=worker_id, api_key="key-1", api_secret="sec", symbol="BTC/USDT")


def _trade(tid: str, ts: int):
    return {
        "id": tid,
        "timestamp": ts,
        "amount": 0.01,
        "price": 50000.0,
        "side": "buy",
        "orderType": None,
        "fee": {"cost": 0.0, "currency": "USDT"},
        "info": {"clientOrderId": f"co-{tid}", "orderId": 1},
    }


def test_account_id_for_key_is_stable_and_masked():
    expect = sha1(b"key-1").hexdigest()[:8]
    assert lts.account_id_for_key("key-1") == expect
    assert lts.account_id_for_key("key-1") == lts.account_id_for_key("key-1")
    assert lts.account_id_for_key("key-2") != expect


def test_load_save_cursor_roundtrip(engine_session):
    session = engine_session["session"]
    assert lts.load_cursor(1, "acc") is None

    lts.save_cursor(session, 1, "acc", 111, "t1")
    lts.save_cursor(session, 1, "acc", 222, "t2")  # 同键 upsert：取大 ts，trade_id 覆盖
    session.commit()

    assert lts.load_cursor(1, "acc") == (222, "t2")
    assert lts.load_cursor(2, "acc") is None  # 其他 worker 隔离


def test_init_reads_cursor_or_falls_back(engine_session, monkeypatch):
    _patch_flags(monkeypatch, cursor_enabled=True)
    monkeypatch.setattr(lts, "BinanceExchange", _FakeExchange)

    # 无游标 → 旧行为（起点=构造时刻）
    s = _make_sync()
    assert s._since == NOW_MS

    # 有游标 → 续拉
    lts.save_cursor(engine_session["session"], 1, lts.account_id_for_key("key-1"), 123456, "t0")
    s2 = _make_sync()
    assert s2._since == 123456


def test_init_cursor_disabled_falls_back(engine_session, monkeypatch):
    monkeypatch.setattr(lts, "BinanceExchange", _FakeExchange)
    _patch_flags(monkeypatch, cursor_enabled=False)
    lts.save_cursor(engine_session["session"], 1, lts.account_id_for_key("key-1"), 1, "t0")

    s = _make_sync()
    assert s._since == NOW_MS, "开关关闭时回退旧行为，忽略持久化游标"


def test_sync_once_persists_cursor(engine_session, monkeypatch):
    _patch_flags(monkeypatch, cursor_enabled=True)
    monkeypatch.setattr(lts, "BinanceExchange", _FakeExchange)
    s = _make_sync()
    s.exchange.exchange._trades = [
        _trade("a", NOW_MS - 5000),
        _trade("b", NOW_MS - 1000),
    ]

    inserted = s.sync_once()

    assert inserted == 2
    assert engine_session["session"].query(WorkerTrade).count() == 2
    cursor = lts.load_cursor(1, lts.account_id_for_key("key-1"))
    assert cursor == (NOW_MS - 1000, "b"), "游标应推进到本轮最大时间戳"

    # 二轮重拉同一批（模拟重启）：trade_id 查重跳过，游标不回退
    s2 = _make_sync()
    assert s2._since == NOW_MS - 1000
    assert s2.sync_once() == 0
    assert engine_session["session"].query(WorkerTrade).count() == 2
    assert lts.load_cursor(1, lts.account_id_for_key("key-1")) == (NOW_MS - 1000, "b")


def test_sync_once_cursor_disabled_no_write(engine_session, monkeypatch):
    _patch_flags(monkeypatch, cursor_enabled=False)
    monkeypatch.setattr(lts, "BinanceExchange", _FakeExchange)
    s = _make_sync()
    s.exchange.exchange._trades = [_trade("a", NOW_MS - 5000)]

    assert s.sync_once() == 1
    assert engine_session["session"].query(WorkerSyncCursor).count() == 0


def test_backfill_warn_and_truncate(engine_session, monkeypatch):
    _patch_flags(monkeypatch, cursor_enabled=True)
    monkeypatch.setattr(lts, "BinanceExchange", _FakeExchange)

    # gap 8h：告警阈值之上、截断阈值之下
    lts.save_cursor(engine_session["session"], 1, lts.account_id_for_key("key-1"), NOW_MS - 8 * 3600_000, "t0")
    s = _make_sync()
    gap_hours, warned, truncated = s.backfill_from_cursor()
    assert 7.9 < gap_hours < 8.1
    assert warned is True
    assert truncated is False
    assert s._since == NOW_MS - 8 * 3600_000, "未截断时起点不动"

    # gap 30h：截断为最近 24h 并写回游标，避免下次重启重复截断
    lts.save_cursor(engine_session["session"], 2, lts.account_id_for_key("key-1"), NOW_MS - 30 * 3600_000, "t0")
    s2 = _make_sync(worker_id=2)
    gap_hours2, warned2, truncated2 = s2.backfill_from_cursor()
    assert 29.9 < gap_hours2 < 30.1
    assert warned2 is True
    assert truncated2 is True
    assert s2._since == NOW_MS - lts.CURSOR_TRUNCATE_GAP_MS
    assert lts.load_cursor(2, lts.account_id_for_key("key-1"))[0] == NOW_MS - lts.CURSOR_TRUNCATE_GAP_MS

    # gap 2h：阈值之下，静默
    lts.save_cursor(engine_session["session"], 3, lts.account_id_for_key("key-1"), NOW_MS - 2 * 3600_000, "t0")
    s3 = _make_sync(worker_id=3)
    _, warned3, truncated3 = s3.backfill_from_cursor()
    assert warned3 is False and truncated3 is False
