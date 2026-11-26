"""LiveTradeSync 最小自检：ccxt 符号推导 + trade 字段映射 + sync_once 订单落库（sqlite 内存 DB）。"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import strategy.models
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
    assert d["fill_id"] == "373270969"
    assert d["symbol"] == "BTC/USDT"
    assert d["side"] == "buy"
    assert d["order_type"] == "MARKET"
    assert d["quantity"] == 0.5
    assert d["price"] == 60000.0
    assert d["notional"] == 30000.0
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
    assert o1.filled_quantity == pytest.approx(0.5)
    assert o1.avg_fill_price == pytest.approx(60000.0)
    assert o1.venue_order_id == "o1"
    # 成交行同步落库（既有行为不回归）
    assert len(db.scalars(select(WorkerTrade)).all()) == 2

    # 同批重拉：trade 查重命中 → 订单 upsert 不触发，无重复行
    assert s.sync_once() == 0
    with factory() as db:
        assert len(db.scalars(select(WorkerOrder)).all()) == 2


def test_sync_positions_upsert_and_close(monkeypatch):
    """持仓对账落库：交易所为权威源——OPEN 行 upsert，平仓后 CLOSE（幻影持仓根治点）。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(lts, "get_db_session", factory)
    from worker.models import WorkerPosition

    s = _make_sync()
    venue_long = [
        {
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "contracts": 0.5,
            "entryPrice": 60000.0,
            "markPrice": 61000.0,
            "unrealizedPnl": 500.0,
            "initialMargin": 3050.0,
            "notional": 30500.0,
            "leverage": 10,
            "liquidationPrice": 55000.0,
            "info": {"breakEvenPrice": "60120.5", "marginRatio": "0.0198"},
        },
        # 合约数为 0 的回报行（交易所空仓也返回条目）必须被过滤
        {"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 0},
    ]
    monkeypatch.setattr(s.exchange.exchange, "fetch_positions", lambda symbols=None: venue_long)

    assert s.sync_positions() == 1
    with factory() as db:
        rows = db.scalars(select(WorkerPosition)).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.position_id == "live:7:BTC/USDT"
    assert row.symbol == "BTC/USDT"
    assert row.status == "OPEN"
    assert row.position_side == "long"
    assert row.quantity == pytest.approx(0.5)
    assert row.entry_price == pytest.approx(60000.0)
    assert row.current_price == pytest.approx(61000.0)
    assert row.unrealized_pnl == pytest.approx(500.0)
    assert row.margin_used == pytest.approx(3050.0)
    # 交易所富化列：杠杆直取、两平价/强平价原生透出、保证金比率×100 百分比口径
    assert row.leverage == pytest.approx(10.0)
    assert row.breakeven_price == pytest.approx(60120.5)
    assert row.liquidation_price == pytest.approx(55000.0)
    assert row.margin_ratio == pytest.approx(1.98)

    # 交易所平仓（空回报）→ OPEN 行收口 CLOSED
    monkeypatch.setattr(s.exchange.exchange, "fetch_positions", lambda symbols=None: [])
    assert s.sync_positions() == 1
    with factory() as db:
        row = db.scalars(select(WorkerPosition)).one()
    assert row.status == "CLOSED"
    assert row.closed_at is not None

    # 重启重演重新持仓 → CLOSED 行复活为 OPEN（position_id 稳定，与 paper 同语义）
    monkeypatch.setattr(s.exchange.exchange, "fetch_positions", lambda symbols=None: venue_long)
    assert s.sync_positions() == 1
    with factory() as db:
        rows = db.scalars(select(WorkerPosition)).all()
    assert len(rows) == 1  # 不另起新行
    assert rows[0].status == "OPEN"


def test_sync_positions_leverage_inferred_when_missing(monkeypatch):
    """demo v3 positionRisk 无 leverage 字段 → 按 名义/初始保证金 推算（与账户总览同款兜底）。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(lts, "get_db_session", factory)
    from worker.models import WorkerPosition

    s = _make_sync()
    venue = [
        {
            "symbol": "ETH/USDT:USDT",
            "side": "long",
            "contracts": 2.0,
            "entryPrice": 1700.0,
            "notional": 3976.63,
            "initialMargin": 795.33,
            "info": {},
        }
    ]
    monkeypatch.setattr(s.exchange.exchange, "fetch_positions", lambda symbols=None: venue)
    assert s.sync_positions() == 1
    with factory() as db:
        row = db.scalars(select(WorkerPosition)).one()
    assert row.leverage == pytest.approx(5.0)
    assert row.breakeven_price is None
    assert row.liquidation_price is None
    assert row.margin_ratio is None


def test_sync_positions_fetch_failure_is_harmless(monkeypatch):
    """fetch_positions 抛错不反噬 tick 循环：记日志返回 0"""
    s = _make_sync()

    def _boom(symbols=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(s.exchange.exchange, "fetch_positions", _boom)
    assert s.sync_positions() == 0
