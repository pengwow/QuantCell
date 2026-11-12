"""P1-03 资金费 / 平仓专项对账验收。

覆盖：funding income 摘要与 venue_absent 单边缺失、现货跳过不落库、
close 配对链两类 break（closed_without_rt / rt_unfilled_pnl，finalize 行
回填断裂）、run_funding_close_reconcile 一条龙。
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import worker.reconciliation as rec
from worker.models import WorkerLog, WorkerPosition, WorkerTrade

WID = 9


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.session.rollback()
        return False


class _FundingExchange:
    """fetch_funding_fees 最小替身（BinanceExchange 实现的同形接口）"""

    def __init__(self, income_rows):
        self._rows = income_rows
        self.calls = []

    def fetch_funding_fees(self, symbol, since_ms):
        self.calls.append((symbol, since_ms))
        return self._rows


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    from collector.db.database import Base, _import_all_models

    _import_all_models()
    engine = create_engine(f"sqlite:///{tmp_path}/funding.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(rec, "get_db_session", lambda: _Ctx(session))
    yield session
    session.close()


def _recon_logs(session):
    return session.query(WorkerLog).filter_by(worker_id=WID, source="reconciliation").all()


def test_funding_summary_then_absent_break(db_session):
    """有持仓 + income 正常 → 摘要落库 ok；窗口内 income 缺失 → venue_absent WARNING"""
    ok = rec.funding_breaks(
        WID,
        _FundingExchange(
            [{"ts_ms": 1, "amount": 0.25, "currency": "USDT"}, {"ts_ms": 2, "amount": -0.1, "currency": "USDT"}]
        ),
        "BTC/USDT:USDT",
        since_ms=0,
        local_positions={"BTC/USDT": 0.5},
        db=db_session,
    )
    assert ok["ok"] is True and ok["income_count"] == 2
    assert ok["income_net"] == {"USDT": pytest.approx(0.15)}
    (row,) = _recon_logs(db_session)
    assert row.level == "INFO" and json.loads(row.message)["ok"] is True

    # 单边缺失：持续在仓（本地影子账非空）而交易所 income 为空
    absent = rec.funding_breaks(
        WID, _FundingExchange([]), "BTC/USDT:USDT", 0, local_positions={"BTC/USDT": 0.5}, db=db_session
    )
    assert absent["ok"] is False and absent["counts"]["venue_absent"] == 1
    (warn,) = [r for r in _recon_logs(db_session) if r.level == "WARNING"]
    assert json.loads(warn.message)["kind"] == "funding"

    # 无交易所 income 但本地无仓（空窗）不误报
    idle = rec.funding_breaks(WID, _FundingExchange([]), "BTC/USDT:USDT", 0, local_positions={}, db=db_session)
    assert idle["ok"] is True and idle["income_count"] == 0


def test_funding_skips_spot(db_session):
    """现货符号（无结算后缀）无资金费概念：不调用交易所、不落库"""
    exch = _FundingExchange([])
    out = rec.funding_breaks(WID, exch, "BTC/USDT", 0, local_positions={}, db=db_session)
    assert out.get("skipped") == "spot"
    assert exch.calls == [] and _recon_logs(db_session) == []


def _add_trade(session, trade_id, symbol, rt=None, pnl=0.25):
    session.add(
        WorkerTrade(
            worker_id=WID,
            trade_id=trade_id,
            symbol=symbol,
            side="buy",
            order_type="market",
            quantity=1.0,
            price=100.0,
            amount=100.0,
            round_trip_id=rt,
            realized_pnl=pnl,
        )
    )


def test_close_consistency_healthy(db_session):
    """正常配对：finalize 行已回填 pnl + 无 CLOSED 残破 → ok"""
    # 一组正常 rt：组键尾部 fill7，finalize 行 trade_id=...:fill7:...，pnl 已回填
    _add_trade(db_session, "paper:9:fill7:100", "BTC/USDT", rt="rt:9:fill7", pnl=-2.5)
    _add_trade(db_session, "paper:9:fill2:90", "BTC/USDT", rt="rt:9:fill7", pnl=None)

    out = rec.close_consistency(WID, db=db_session)
    assert out["ok"] is True and out["counts"] == {"closed_without_rt": 0, "rt_unfilled_pnl": 0}


def test_close_consistency_breaks(db_session):
    """两类 break：CLOSED 无配对组 + finalize 行盈亏未回填 → WARNING 落库"""
    # break 1：ETH 有 CLOSED 持仓且有成交、但零 rt 组（配对链完全断裂）
    db_session.add(
        WorkerPosition(
            worker_id=WID,
            position_id="pos1",
            symbol="ETH/USDT",
            side="LONG",
            quantity=0.0,
            entry_price=1.0,
            status="CLOSED",
        )
    )
    _add_trade(db_session, "paper:9:fill3:88", "ETH/USDT")  # 无 rt 组
    # break 2：rt 组产出但 finalize 行 realized_pnl 为 NULL（回填断裂）
    _add_trade(db_session, "paper:9:fill7:100", "BTC/USDT", rt="rt:9:fill7", pnl=None)
    db_session.commit()

    out = rec.close_consistency(WID, db=db_session)
    assert out["ok"] is False
    assert out["counts"] == {"closed_without_rt": 1, "rt_unfilled_pnl": 1}
    assert out["symbols"] == ["ETH/USDT"]
    (row,) = _recon_logs(db_session)
    assert row.level == "WARNING" and json.loads(row.message)["kind"] == "close"


def test_binance_fetch_funding_fees_symbol_mapping():
    """BinanceExchange 实现：统一符号去后缀转 market_id、income 字段按 ts/amount/currency 逐笔透出"""
    from exchange.binance.exchange import BinanceExchange

    class _Ccxt:
        def fapiPrivate_get_income(self, params):
            assert params == {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "startTime": 5, "limit": 1000}
            return [{"time": 10, "income": "0.25", "asset": "USDT"}, {"time": 20, "income": "-0.10", "asset": "USDT"}]

    exch = BinanceExchange.__new__(BinanceExchange)  # 绕开 ccxt.binance(config) 网络配置
    exch.exchange = _Ccxt()
    rows = exch.fetch_funding_fees("BTC/USDT:USDT", since_ms=5)
    assert rows == [
        {"ts_ms": 10, "symbol": "BTC/USDT:USDT", "amount": 0.25, "currency": "USDT"},
        {"ts_ms": 20, "symbol": "BTC/USDT:USDT", "amount": -0.10, "currency": "USDT"},
    ]


def test_run_funding_close_reconcile_critical(tmp_path, db_session):
    """一条龙：funding（spot 跳过后仍保留 close）→ 返回落库摘要列表"""
    from types import SimpleNamespace

    class _Driver:
        def snapshot(self):
            # 引擎 LocalSnapshot 是属性对象（.positions），非 dict
            return SimpleNamespace(positions={"BTC/USDT": 0.5}, cash=1.0, fill_ids=[])

    _add_trade(db_session, "paper:9:fill7:100", "BTC/USDT", rt="rt:9:fill7", pnl=1.2)
    db_session.commit()

    out = rec.run_funding_close_reconcile(
        WID,
        _Driver(),
        _FundingExchange([{"ts_ms": 1, "amount": 0.5, "currency": "USDT"}]),
        "BTC/USDT:USDT",
        since_ms=0,
        db=db_session,
    )
    assert [item["kind"] for item in out] == ["funding", "close"]
    assert all(item["ok"] for item in out)
    assert len(_recon_logs(db_session)) == 2  # 每类各落一条
