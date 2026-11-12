"""P1-02 对账落盘导入与运行期周期对账验收。

覆盖：ok/fail 报告写入 worker_logs（level/摘要）、内容不变不重复落库、
venue 快照口径（signed 净额 / cash 扣未实现 / fill 窗口覆盖型）、
周期对账一条龙（snapshot → reconcile → 落盘 → 入库）。
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import worker.reconciliation as rec
from worker.models import WorkerLog

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


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    """sqlite 内存库 + reconciliation 模块级 get_db_session 指向它"""
    from collector.db.database import Base, _import_all_models

    _import_all_models()  # 先注册全部模型，否则外键表缺失 create_all 会炸
    engine = create_engine(f"sqlite:///{tmp_path}/recon.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(rec, "get_db_session", lambda: _Ctx(session))
    yield session
    session.close()


class _FakeCcxt:
    def __init__(self, positions=None, balance=None, trades=None):
        self._positions = positions or []
        self._balance = balance or {"total": {"USDT": 0.0}}
        self._trades = trades or []

    def fetch_positions(self, symbols):
        return self._positions

    def fetch_balance(self):
        return self._balance

    def fetch_my_trades(self, symbol, since=None, limit=None):
        return self._trades


class _FakeExchange:
    def __init__(self, ccxt):
        self.exchange = ccxt


class _FakeDriver:
    """driver.snapshot() 的最小替身：本地影子账三资"""

    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self):
        return self._snapshot


def _journal_dir(tmp_path) -> str:
    d = tmp_path / "live"
    d.mkdir(exist_ok=True)
    return str(d)


def _write_report(journal_dir: str, ok: bool, payload: dict):
    name = f"worker_{WID}." + ("reconcile_last_ok.json" if ok else "reconcile.json")
    Path(journal_dir, name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_import_ok_and_fail_reports(db_session, tmp_path):
    journal_dir = _journal_dir(tmp_path)
    _write_report(
        journal_dir,
        ok=False,
        payload={
            "position_breaks": [],
            "missing_fills": ["1"],
            "extra_fills": [],
            "ghost_orders": [],
            "orphan_local_orders": [],
            "cash_break": {"venue": 1.0, "local": 2.0},
        },
    )
    _write_report(
        journal_dir,
        ok=True,
        payload={
            "position_breaks": [],
            "missing_fills": [],
            "extra_fills": [],
            "ghost_orders": [],
            "orphan_local_orders": [],
            "cash_break": None,
        },
    )

    imported = rec.import_reconcile_reports(WID, journal_dir)
    assert len(imported) == 2

    rows = db_session.query(WorkerLog).filter_by(worker_id=WID, source="reconciliation").all()
    assert len(rows) == 2
    by_level = {r.level: json.loads(r.message) for r in rows}
    fail = next(v for v in by_level.values() if not v["ok"])
    ok = next(v for v in by_level.values() if v["ok"])
    assert fail["counts"]["missing_fills"] == 1 and fail["counts"]["cash_break"] == 1
    assert ok["counts"]["cash_break"] == 0


def test_import_skip_unchanged(db_session, tmp_path):
    journal_dir = _journal_dir(tmp_path)
    _write_report(
        journal_dir,
        ok=True,
        payload={
            "position_breaks": [],
            "missing_fills": [],
            "extra_fills": [],
            "ghost_orders": [],
            "orphan_local_orders": [],
            "cash_break": None,
        },
    )
    assert len(rec.import_reconcile_reports(WID, journal_dir)) == 1
    # 内容未变：hash 相同不重复落库（防周期导入刷屏）
    assert rec.import_reconcile_reports(WID, journal_dir) == []


def test_build_venue_snapshot_caliber():
    """positions 签名净额（long+short 互抵、key 归一 BASE/QUOTE）、cash 扣未实现、fill 去重"""
    ccxt = _FakeCcxt(
        positions=[
            {"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 1.5, "unrealizedPnl": 100.0},
            {"symbol": "BTC/USDT:USDT", "side": "short", "contracts": 0.5, "unrealizedPnl": -30.0},
            {"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 0.0, "unrealizedPnl": 0.0},
        ],
        balance={"total": {"USDT": 12_000.0}},
        trades=[{"id": "2"}, {"id": "1"}, {"id": "2"}, {"id": None}],
    )
    venue = rec.build_venue_snapshot(_FakeExchange(ccxt), "BTC/USDT:USDT")
    assert venue["positions"] == {"BTC/USDT": 1.0}
    assert venue["cash"] == 12_000.0 - (100.0 - 30.0)
    assert venue["fill_ids"] == ["1", "2"]


def test_run_periodic_reconcile_clean_writes_ok_report(db_session, tmp_path):
    """干净对账：落盘 *_reconcile_last_ok.json 并 INFO 落库"""
    journal_dir = _journal_dir(tmp_path)
    driver = _FakeDriver({"positions": {"BTC/USDT": 0.5}, "cash": 10_000.0, "fill_ids": ["7"]})
    ccxt = _FakeCcxt(
        positions=[{"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 0.5, "unrealizedPnl": 0.0}],
        balance={"total": {"USDT": 10_000.0}},
        trades=[{"id": "7"}],
    )

    imported = rec.run_periodic_reconcile(WID, driver, _FakeExchange(ccxt), "BTC/USDT:USDT", journal_dir)

    assert len(imported) == 1 and imported[0]["ok"] is True
    on_disk = json.loads(Path(journal_dir, f"worker_{WID}.reconcile_last_ok.json").read_text())
    assert on_disk["position_breaks"] == []


def test_recent_reconcile_summaries(db_session, tmp_path):
    """API 读取摘要：只收 source=reconciliation、新→旧、脏 JSON 降级 raw"""
    from datetime import UTC, datetime, timedelta

    base = datetime.now(UTC)
    # 显式递增时间戳：同秒日志 desc 排序不稳定，断言不依赖排序实现细节
    # 一条其它 source 的日志 + 一条正常对账日志 + 一条脏 JSON
    db_session.add(WorkerLog(worker_id=WID, level="INFO", message="无关日志", timestamp=base))
    db_session.add(
        WorkerLog(
            worker_id=WID,
            level="WARNING",
            source="reconciliation",
            message=json.dumps({"ok": False, "counts": {"cash_break": 1}}),
            timestamp=base + timedelta(seconds=1),
        )
    )
    db_session.add(
        WorkerLog(
            worker_id=WID,
            level="INFO",
            source="reconciliation",
            message="不是JSON的旧消息",
            timestamp=base - timedelta(seconds=1),
        )
    )
    db_session.commit()

    out = rec.recent_reconcile_summaries(WID, 5, db=db_session)
    assert len(out) == 2  # 无 source 的日志被过滤
    assert out[0]["ok"] is False and out[0]["counts"]["cash_break"] == 1
    assert out[1] == {"timestamp": out[1]["timestamp"], "level": "INFO", "raw": "不是JSON的旧消息"}
