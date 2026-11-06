"""多 worker 作业租约（factor/job_lease.py）：判活、跨进程 stop 标志、心跳线程联测。"""

import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import strategy.models
from collector.db.database import Base
from factor import job_lease, job_manager
from factor.models import FactorMiningRun
from research.models import ResearchSession


@pytest.fixture
def db():
    """内存 SQLite，只建两张租约影子表（其余用例不需要）。"""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[FactorMiningRun.__table__, ResearchSession.__table__])
    with sessionmaker(bind=eng)() as s:
        yield s


def _add_mining(db, job_id, status="running", hb=None):
    row = FactorMiningRun(job_id=job_id, status=status, params_json="{}")
    if hb is not None:
        row.heartbeat_at = hb
    db.add(row)
    db.commit()
    return row


def _add_session(db, job_id, status="running", hb=None, cancel=0, pause=0):
    row = ResearchSession(
        owner_id="u1",
        name="t",
        backend_job_id=job_id,
        status=status,
        heartbeat_at=hb,
        cancel_requested=cancel,
        pause_requested=pause,
    )
    db.add(row)
    db.commit()
    return row


# ---------- 判活 ----------


def test_mining_lease_alive_only_when_running_and_fresh(db):
    _add_mining(db, "alive", "running", hb=time.time())
    _add_mining(db, "stale", "running", hb=time.time() - 999)
    _add_mining(db, "null", "running")
    _add_mining(db, "done", "completed", hb=time.time())

    assert job_lease.has_fresh_mining_lease("alive", db=db)
    assert not job_lease.has_fresh_mining_lease("stale", db=db)
    # NULL 视为不活跃：崩溃残留行可被懒修正/重跑兜住
    assert not job_lease.has_fresh_mining_lease("null", db=db)
    assert not job_lease.has_fresh_mining_lease("done", db=db)
    assert not job_lease.has_fresh_mining_lease("no-such-job", db=db)


def test_session_lease_same_semantics(db):
    _add_session(db, "j1", "running", hb=time.time())
    _add_session(db, "j2", "cancelled", hb=time.time())

    assert job_lease.has_fresh_session_lease("j1", db=db)
    assert not job_lease.has_fresh_session_lease("j2", db=db)
    assert not job_lease.has_fresh_session_lease("no-such-job", db=db)


# ---------- 跨进程 cancel/pause 标志 ----------


def test_consume_session_signal_read_and_clear(db):
    _add_session(db, "j1", "running", hb=time.time())
    assert not job_lease.consume_session_signal("j1", "cancel", db=db)

    job_lease.request_session_stop("j1", "cancel", db=db)
    assert job_lease.consume_session_signal("j1", "cancel", db=db)
    # 清零后不再重复消费
    assert not job_lease.consume_session_signal("j1", "cancel", db=db)


def test_request_unknown_signal_rejected(db):
    with pytest.raises(KeyError):
        job_lease.request_session_stop("j1", "shutdown", db=db)


def test_clear_session_stop_resets_both_flags(db):
    _add_session(db, "j1", "running", hb=time.time(), cancel=1, pause=1)
    job_lease.clear_session_stop(1, db=db)
    assert not job_lease.consume_session_signal("j1", "cancel", db=db)
    assert not job_lease.consume_session_signal("j1", "pause", db=db)


def test_consume_matches_only_backend_job_id(db):
    # 标志绑定 backend_job_id：别的会话/新作业读不到旧作业的标志
    _add_session(db, "j1", "running", hb=time.time(), cancel=1)
    assert not job_lease.consume_session_signal("j2", "cancel", db=db)


# ---------- 心跳线程联测（fake 租约钩子，短 tick） ----------


def _submit_blocked(mgr, lease, holder, hb_calls, stop_calls, monkeypatch):
    """提交一个被 holder event 阻塞的作业，hook 走注入的 fake 钩子。"""

    def _heartbeat(job_id):
        hb_calls.append(job_id)

    def _poll(job_id, sig):
        # cancel 信号只触发一次
        if sig == "cancel" and not stop_calls:
            stop_calls.append((job_id, sig))
            return True
        return False

    monkeypatch.setitem(
        job_manager.LEASE_HOOKS,
        lease,
        {"heartbeat": _heartbeat, "poll_signal": _poll},
    )
    stop_cb_calls = []
    mgr.submit(
        "lease-test",
        {},
        lambda p, q, e: holder.wait(2),
        lease=lease,
        on_stop_signal=lambda sig: stop_cb_calls.append(sig),
    )
    return stop_cb_calls


def test_heartbeat_loop_writes_and_consumes_stop_signal(monkeypatch):
    holder = threading.Event()
    hb_calls, stop_flags = [], []
    mgr = job_manager.FactorJobManager(max_workers=2, heartbeat_interval=0.05)
    try:
        # stop_cb_calls 由 _submit_blocked 返回（on_stop_signal 闭包持有它）
        stop_cb_calls = _submit_blocked(mgr, "fake", holder, hb_calls, stop_flags, monkeypatch)
        # 轮询等待心跳线程消费 cancel 信号（holder 用来阻塞 runner，不能当等待信号用）
        deadline = time.time() + 2.0
        while time.time() < deadline and not stop_cb_calls:
            time.sleep(0.02)
        holder.set()  # 放行 runner，让作业结束、线程池回收
        assert hb_calls, "心跳未被写入"
        assert stop_cb_calls == ["cancel"], f"跨进程 cancel 未拉起本地信号: {stop_cb_calls}"
    finally:
        mgr.shutdown()
        holder.set()


def test_heartbeat_loop_skips_jobs_without_lease(monkeypatch):
    holder = threading.Event()
    touched = []
    mgr = job_manager.FactorJobManager(max_workers=2, heartbeat_interval=0.05)
    try:
        # lease=None（默认，无 DB 行的作业）不进入租约循环：挂 None key 钩子，漏过滤立即可见
        monkeypatch.setitem(
            job_manager.LEASE_HOOKS,
            None,
            {"heartbeat": lambda j: touched.append(j), "poll_signal": lambda *a: False},
        )
        mgr.submit("lease-none", {}, lambda p, q, e: holder.wait(0.3))
        deadline = time.time() + 3.0
        while time.time() < deadline and (mgr.get_status("lease-none") or {}).get("status") in ("pending", "running"):
            time.sleep(0.02)
        holder.set()
        assert not touched, "无租约的作业被写入了心跳"
    finally:
        mgr.shutdown()
        holder.set()


# ---------- ensure_lease_columns 迁移（幂等） ----------


def test_ensure_lease_columns_idempotent(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(
            text("CREATE TABLE factor_mining_runs (id INTEGER PRIMARY KEY, job_id VARCHAR(64), status VARCHAR(16))")
        )
        conn.execute(
            text(
                "CREATE TABLE research_sessions (id INTEGER PRIMARY KEY, backend_job_id VARCHAR(64), status VARCHAR(16))"
            )
        )
    with sessionmaker(bind=eng)() as s:
        job_lease.ensure_lease_columns(s, "sqlite")
        cols1 = {c["name"] for c in inspect(eng).get_columns("factor_mining_runs")}
        cols2 = {c["name"] for c in inspect(eng).get_columns("research_sessions")}
        assert "heartbeat_at" in cols1
        assert {"heartbeat_at", "cancel_requested", "pause_requested"} <= cols2
        # 幂等：重复执行不抛错、不加重复列
        job_lease.ensure_lease_columns(s, "sqlite")
        assert "heartbeat_at" in {c["name"] for c in inspect(eng).get_columns("factor_mining_runs")}

    # 补列后旧表可直接写心跳
    with sessionmaker(bind=eng)() as s:
        s.execute(text("INSERT INTO factor_mining_runs (job_id, status) VALUES ('j', 'running')"))
        s.commit()
        job_lease.mark_mining_heartbeat("j", db=s)
        raw = s.execute(text("SELECT heartbeat_at FROM factor_mining_runs WHERE job_id='j'")).one()
        assert raw[0] is not None


# ---------- reconcile 与租约判活的组合行为 ----------


def test_reconcile_keeps_running_when_lease_fresh(db_session, monkeypatch):
    # 不用 conftest 的 svc fixture：那返回 FactorService，这里需要 MiningRunService
    from factor.mining_run_service import MiningRunService
    from tests.unit.factor.test_mining_run_service import _StubJobManager

    msvc = MiningRunService()
    msvc.create_running(db_session, "job-remote", {"instruments": ["BTCUSDT"]})
    # 内存查无此 job（当前进程不是持有者），但租约心跳新鲜 → 其它进程在跑，不得误杀
    monkeypatch.setattr("factor.mining_run_service.job_manager", _StubJobManager({}))
    _, runs = msvc.list_runs(db_session)
    assert runs[0].status == "running"


def test_reconcile_marks_interrupted_when_lease_stale(db_session, monkeypatch):
    from factor.mining_run_service import MiningRunService
    from tests.unit.factor.test_mining_run_service import _StubJobManager

    msvc = MiningRunService()
    row = msvc.create_running(db_session, "job-stale", {"instruments": ["BTCUSDT"]})
    row.heartbeat_at = time.time() - 999
    db_session.commit()
    monkeypatch.setattr("factor.mining_run_service.job_manager", _StubJobManager({}))
    _, runs = msvc.list_runs(db_session)
    assert runs[0].status == "interrupted"
