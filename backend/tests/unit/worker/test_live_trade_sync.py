"""LiveTradeSync 最小自检：ccxt 符号推导 + trade 字段映射 + sync_once 订单落库（sqlite 内存 DB）。"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import worker.live_trade_sync as lts
from collector.db.database import Base
from worker.live_trade_sync import LiveTradeSync
from worker.models import WorkerOrder, WorkerTrade


@pytest.fixture(autouse=True)
def _no_cursor_db(monkeypatch):
    """本文件只测纯逻辑：关闭同步游标开关，__init__ 不读真库游标"""
    monkeypatch.setattr(lts, "get_flag", lambda key, default=True: False)


def _make_sync() -> LiveTradeSync:
    # 构造不联网：ccxt 实例纯对象装配（credentials 为假值，不发起请求）
    return LiveTradeSync(worker_id=7, api_key="k", api_secret="s", symbol="BTC/USDT")


def test_ccxt_symbol_suffix_and_since():
    s = _make_sync()
    assert s._ccxt_symbol == "BTC/USDT:USDT"
    assert s._since > 0
    # DB symbol 口径与 LiveTradeRecorder（instrument_id）一致
    assert s.symbol == "BTC/USDT"


def test_to_trade_data_mapping():
    s = _make_sync()
    trade = {
        "id": "373270969",
        "side": "buy",
        "amount": 0.5,
        "price": 60000.0,
        "timestamp": 1750000000000,
        "fee": {"cost": 0.03, "currency": "USDT"},
        "info": {"realizedPnl": "12.5"},
    }
    d = s._to_trade_data(trade)
    assert d["worker_id"] == 7
    assert d["trade_id"] == "373270969"
    assert d["symbol"] == "BTC/USDT"
    assert d["side"] == "buy"
    assert d["order_type"] == "MARKET"
    assert d["quantity"] == 0.5
    assert d["price"] == 60000.0
    assert d["amount"] == 30000.0
    assert d["fee"] == 0.03
    assert d["fee_currency"] == "USDT"
    assert d["realized_pnl"] == 12.5
    assert d["realized_pnl_pct"] is None
    assert d["entry_time"] == datetime.fromtimestamp(1750000000)
    assert d["exit_time"] is None
    # 新契约键：现货/无 positionSide 回报兜底 both（声明值，不从 side 推导）；trade 行 reduce_only 恒 False
    assert d["position_side"] == "both"
    assert d["reduce_only"] is False


def test_to_trade_data_missing_fields():
    s = _make_sync()
    d = s._to_trade_data({"id": "1", "side": "buy"})
    assert d["order_type"] == "MARKET"
    assert d["fee"] == 0.0
    assert d["fee_currency"] == "USDT"
    assert d["realized_pnl"] is None
    assert d["entry_time"] is None
    # side 缺失属脏回报：vocab 归一层抛 ValueError，由 sync_once 兜底中断本轮（脏路径不落盘）
    with pytest.raises(ValueError):
        s._to_trade_data({"id": "1"})


def test_to_trade_data_bad_realized_pnl():
    s = _make_sync()
    d = s._to_trade_data({"id": "2", "side": "sell", "info": {"realizedPnl": "abc"}})
    assert d["realized_pnl"] is None


def test_sync_once_persists_order_rows(monkeypatch):
    """成交落库时以 clientOrderId 落 FILLED 订单行；重拉查重命中不重复累加。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(lts, "get_db_session", factory)

    ts = 1750000000000
    trades = [
        {
            "id": "373270969",
            "side": "buy",
            "amount": 0.5,
            "price": 60000.0,
            "timestamp": ts,
            "fee": {"cost": 0.03, "currency": "USDT"},
            "orderType": "market",
            "info": {"clientOrderId": "c1", "orderId": "o1"},
        },
        {
            "id": "373270970",
            "side": "sell",
            "amount": 0.5,
            "price": 61000.0,
            "timestamp": ts + 1000,
            "fee": {"cost": 0.03, "currency": "USDT"},
            "info": {"orderId": "o2"},  # 无 clientOrderId → 退 venue orderId
        },
    ]
    s = _make_sync()
    monkeypatch.setattr(s.exchange.exchange, "fetch_my_trades", lambda symbol, since=None: trades)

    assert s.sync_once() == 2
    with factory() as db:
        orders = {o.client_order_id: o for o in db.scalars(select(WorkerOrder)).all()}
    assert set(orders) == {"c1", "o2"}
    o1 = orders["c1"]
    assert o1.status == "FILLED"
    # 落库方向词汇统一为 canonical 小写（上游原词大小写由 crud 归一）
    assert o1.side == "buy"
    assert o1.symbol == "BTC/USDT"
    assert o1.order_type == "MARKET"
    assert o1.filled_qty == pytest.approx(0.5)
    assert o1.avg_fill_price == pytest.approx(60000.0)
    assert o1.venue_order_id == "o1"
    # 成交行同步落库（既有行为不回归）
    assert len(db.scalars(select(WorkerTrade)).all()) == 2

    # 同批重拉：trade 查重命中 → 订单 upsert 不触发，无重复行
    assert s.sync_once() == 0
    with factory() as db:
        assert len(db.scalars(select(WorkerOrder)).all()) == 2
