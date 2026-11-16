"""risk_status_snapshot 三态组装与熔断推导的单测（spec 2026-11-16 §4.1）。

隔离方式对齐 test_risk_control_api.py 的"接管 DB 入口"思路，但 patch 点更深一层：
Load 行走 _load_risk_control_row → utils.db_session.get_db_session；
若只 patch collector.db.database.SessionLocal，get_db_session 首次调用会触发
init_database_config() 对"当前 SessionLocal"执行 configure(bind=真实文件引擎)，
sessionmaker.configure 原地改写被 patch 进来的 sessionmaker 的 bind，查询会泄漏到
开发库（test_risk_control_api 靠 client fixture 先拉起 app 完成初始化避开此坑）。
直接 patch get_db_session 本尊（函数内每次动态 import，patch 必然生效）则完全无副作用。
"""

from contextlib import contextmanager

import pytest
from sqlalchemy.orm import sessionmaker

from worker import models
from worker.risk_config import risk_status_snapshot


@pytest.fixture
def db(db_engine, monkeypatch):
    """自建 DB fixture：conftest 无名为 db 的 fixture，且其共享内存库行会跨用例残留。

    接管 get_db_session 后 _load_risk_control_row 查到本用例数据；
    用例结束清空 risk 表，避免 worker_id 唯一约束跨用例冲突。
    """
    import utils.db_session as db_session_mod

    sm = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    @contextmanager
    def _fake_get_db_session():
        session = sm()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(db_session_mod, "get_db_session", _fake_get_db_session)
    session = sm()
    yield session
    session.close()
    with db_engine.begin() as conn:
        conn.execute(models.WorkerRiskControl.__table__.delete())


def _make_row(db, worker_id: int, **kw) -> None:
    db.add(models.WorkerRiskControl(worker_id=worker_id, **kw))
    db.commit()


def test_none_when_no_row_and_no_params(db):
    out = risk_status_snapshot({}, worker_id=1, initial_cash=100_000.0, daily_pnl=None)
    assert out["configured"] is False
    assert out["source"] == "none"
    assert out["enabled"] is False
    assert out["config"] is None
    assert out["circuit_breaker_tripped"] is False


def test_manual_enabled_maps_config(db):
    # max_position_size 显式写大值（upsert 规范：字段须显式写值含 None），
    # 使金额口径取 pct×cash；绝对金额与比例并存时 _map_row_to_settings 取更严者，
    # 99999 > 50000 故 max_position_value 仍是 0.5×100000=50000
    _make_row(
        db,
        1,
        enabled=True,
        max_position_size=99999.0,
        max_position_pct=0.5,
        daily_loss_amount=2000.0,
        max_drawdown=0.2,
        max_leverage=5.0,
    )
    out = risk_status_snapshot({}, worker_id=1, initial_cash=100_000.0, daily_pnl=-1200.5)
    assert out["configured"] and out["source"] == "manual" and out["enabled"]
    assert out["config"]["max_position_value"] == 50000.0
    assert out["daily_loss_limit"] == 2000.0
    assert out["loss_usage"] == pytest.approx(0.60025)
    assert out["circuit_breaker_tripped"] is False
    assert out["tripped_source"] == "derived"


def test_manual_disabled_has_no_live_config(db):
    _make_row(db, 1, enabled=False)
    out = risk_status_snapshot({}, worker_id=1, initial_cash=100_000.0, daily_pnl=-999.0)
    assert out["configured"] and out["source"] == "manual"
    assert out["enabled"] is False
    assert out["config"] is None
    assert out["circuit_breaker_tripped"] is False  # 停用态不推导


def test_params_passthrough(db):
    params = {"risk": {"max_position_value": 3000.0, "max_daily_loss": 500.0}}
    out = risk_status_snapshot(params, worker_id=1, initial_cash=100_000.0, daily_pnl=-100.0)
    assert out["configured"] and out["source"] == "params" and out["enabled"]
    assert out["config"]["max_position_value"] == 3000.0
    assert out["daily_loss_limit"] == 500.0
    assert out["loss_usage"] == pytest.approx(0.2)


def test_tripped_at_boundary(db):
    _make_row(db, 1, enabled=True, daily_loss_amount=2000.0)
    out = risk_status_snapshot({}, worker_id=1, initial_cash=100_000.0, daily_pnl=-2000.0)
    assert out["circuit_breaker_tripped"] is True  # 恰等于额度即触发
    assert out["loss_usage"] == 1.0


def test_tripped_skipped_when_pnl_missing(db):
    _make_row(db, 1, enabled=True, daily_loss_amount=2000.0)
    out = risk_status_snapshot({}, worker_id=1, initial_cash=100_000.0, daily_pnl=None)
    assert out["circuit_breaker_tripped"] is False
    assert out["loss_usage"] is None
