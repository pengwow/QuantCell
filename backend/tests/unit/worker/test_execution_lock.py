"""P0-03 跨 worker 执行锁验收。

覆盖：同 worker 幂等复读、他主互斥、TTL 过期换主自愈、release 释放与
非持锁方无副作用、heartbeat 续期与失锁判定、过期清理、自开短会话路径
的显式 commit（get_db_session 不会自动提交，漏提交会随 close 回滚）。
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import strategy.models
import worker.execution_lock as el
from collector.db.database import Base
from worker.models import OrderLease

SYM = "BTC/USDT"
ACC = "abcd1234"


@pytest.fixture()
def engine_session(monkeypatch, tmp_path):
    """sqlite 文件库 + execution_lock 自开路径（get_db_session）指向它"""
    engine = create_engine(f"sqlite:///{tmp_path}/lease.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    class _Ctx:
        def __enter__(self):
            return session

        def __exit__(self, exc_type, exc, tb):
            if exc is not None:
                session.rollback()
            return False

    monkeypatch.setattr(el, "get_db_session", _Ctx)
    yield session
    session.close()


def _expire_lease(session, symbol: str = SYM) -> None:
    """手工把锁行过期，模拟持有方死亡超 TTL"""
    row = session.execute(select(OrderLease).where(OrderLease.lease_key == el.lease_key(symbol, ACC))).scalar_one()
    row.expires_at = 0.0
    session.commit()


def test_acquire_idempotent_same_worker(engine_session):
    assert el.acquire(SYM, ACC, 1, db=engine_session)
    # 重复 acquire 幂等：本 worker 复读并顺带续期
    assert el.acquire(SYM, ACC, 1, db=engine_session)
    rows = engine_session.query(OrderLease).all()
    assert len(rows) == 1 and rows[0].owner_worker_id == 1


def test_acquire_mutual_exclusive(engine_session):
    assert el.acquire(SYM, ACC, 1, db=engine_session)
    # 他主且新鲜：另一 worker 拿不到，锁行不被改写
    assert not el.acquire(SYM, ACC, 2, db=engine_session)
    row = engine_session.query(OrderLease).one()
    assert row.owner_worker_id == 1


def test_takeover_after_ttl_expiry(engine_session):
    assert el.acquire(SYM, ACC, 1, db=engine_session)
    _expire_lease(engine_session)
    # kill -9 无 release 的死亡：过期行可被他人条件 UPDATE 换主
    assert el.acquire(SYM, ACC, 2, db=engine_session)
    row = engine_session.query(OrderLease).one()
    assert row.owner_worker_id == 2 and row.expires_at > 0


def test_release_and_non_owner_noop(engine_session):
    assert el.acquire(SYM, ACC, 1, db=engine_session)
    # 非持锁方 release 无副作用
    assert not el.release(SYM, ACC, 2, db=engine_session)
    assert engine_session.query(OrderLease).one().owner_worker_id == 1
    # owner 释放后立即可被抢
    assert el.release(SYM, ACC, 1, db=engine_session)
    assert el.acquire(SYM, ACC, 2, db=engine_session)


def test_heartbeat_renew_and_foreign_fail(engine_session):
    assert el.acquire(SYM, ACC, 1, db=engine_session)
    _expire_lease(engine_session)
    # 已过期但未被换主时 owner 仍可续期（expires_at 从 0 恢复为未来时间）
    assert el.heartbeat(SYM, ACC, 1, db=engine_session)
    row = engine_session.query(OrderLease).one()
    assert row.expires_at > 0
    # 非 owner heartbeat 失败且不改锁行（owner 未变、续期不生效）
    renewed = row.expires_at
    assert not el.heartbeat(SYM, ACC, 2, db=engine_session)
    assert engine_session.query(OrderLease).one().expires_at == renewed


def test_sweep_expired_keeps_fresh(engine_session):
    assert el.acquire(SYM, ACC, 1, db=engine_session)
    assert el.acquire("ETH/USDT", ACC, 2, db=engine_session)
    _expire_lease(engine_session, "ETH/USDT")
    assert el.sweep_expired(db=engine_session) == 1
    keys = {r.lease_key for r in engine_session.query(OrderLease).all()}
    assert keys == {el.lease_key(SYM, ACC)}


def test_no_explicit_db_commits(engine_session):
    """自开短会话路径：不传 db，靠 execution_lock 内部显式 commit 落库。
    用独立新会话验证，防 job_lease 那类「写入随 close 回滚」的回归。"""
    assert el.acquire(SYM, ACC, 1)  # 走 monkeypatch 后的自开路径
    fresh = sessionmaker(bind=engine_session.get_bind())()
    try:
        assert fresh.query(OrderLease).one().owner_worker_id == 1
    finally:
        fresh.close()
