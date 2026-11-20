"""五域启动补偿扫描单测。

补偿函数把重启后残留的非终态任务统一收口为「已中断」并发 INTERRUPTED
通知。统一 monkeypatch 各模块命名空间里的 notify_task_event 与 session
工厂（use_db_session / get_db_session / _collector_db_session），用内存
SQLite 真跑扫描查询；不触任何真实业务库。
"""

import contextlib
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backtest.models import BacktestTask
from collector.db.database import Base, _import_all_models
from collector.db.models import Task
from common.notifications.inbox_models import AsyncTaskRecord
from research.models import ResearchSession

# 预注册全部业务模型，避免 Worker 等 relationship 在 mapper 初始化时找不到 Strategy
# （同目录 test_inbox.py 的既有约定）
_import_all_models()


@pytest.fixture()
def comp_sessionmaker():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Task.__table__,
            BacktestTask.__table__,
            ResearchSession.__table__,
            AsyncTaskRecord.__table__,
        ],
    )
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield maker
    engine.dispose()


@contextlib.contextmanager
def _fake_db_session(maker):
    db = maker()
    try:
        yield db
    finally:
        db.close()


def _patch_notify(monkeypatch, target: str):
    calls = []

    def fake(task_type, task_id, status, *, name=None, error=None, extra=None):
        calls.append((task_type, task_id, status, name, error))

    monkeypatch.setattr(target, fake, raising=False)
    return calls


class TestShadowCompensation:
    """rl_train / factor_job：以 async_task_records 影子表为补偿依据"""

    @pytest.mark.parametrize(
        "module_path,task_type",
        [("services.rl_task_runner", "rl_train"), ("factor.job_manager", "factor_job")],
    )
    def test_interrupts_stale_rows(self, comp_sessionmaker, monkeypatch, module_path, task_type):
        import importlib

        mod = importlib.import_module(module_path)
        with comp_sessionmaker() as db:
            db.add_all(
                [
                    AsyncTaskRecord(task_type=task_type, task_id="a1", status="queued", name="A-1"),
                    AsyncTaskRecord(task_type=task_type, task_id="a2", status="running", name="A-2"),
                    AsyncTaskRecord(task_type=task_type, task_id="a3", status="succeeded", name="A-3"),
                    AsyncTaskRecord(task_type="other", task_id="x1", status="running", name="X"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, f"{module_path}.notify_task_event")
        monkeypatch.setattr(f"{module_path}.use_db_session", lambda: _fake_db_session(comp_sessionmaker), raising=False)

        assert mod.compensate_interrupted_tasks() == 2

        with comp_sessionmaker() as db:
            statuses = {r.task_id: r.status for r in db.query(AsyncTaskRecord).all()}
        assert statuses["a1"] == "interrupted"
        assert statuses["a2"] == "interrupted"
        assert statuses["a3"] == "succeeded"  # 已终态不重碰
        assert statuses["x1"] == "running"  # 其它域不误伤

        assert [(c[1], c[2]) for c in calls] == [("a1", "INTERRUPTED"), ("a2", "INTERRUPTED")]
        assert all(c[0] == task_type for c in calls)


class TestCollectorCompensation:
    def test_marks_stale_failed(self, comp_sessionmaker, monkeypatch):
        from collector.utils import task_manager

        with comp_sessionmaker() as db:
            db.add_all(
                [
                    Task(task_id="c1", task_type="crypto_download", status="pending", params="{}"),
                    Task(task_id="c2", task_type="crypto_download", status="running", params="{}"),
                    Task(task_id="c3", task_type="crypto_download", status="completed", params="{}"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, "collector.utils.task_manager.notify_task_event")
        monkeypatch.setattr(task_manager, "_collector_db_session", comp_sessionmaker, raising=False)

        assert task_manager.compensate_interrupted_tasks() == 2

        with comp_sessionmaker() as db:
            rows = {r.task_id: r.status for r in db.query(task_manager.Task).all()}
        assert rows == {"c1": "failed", "c2": "failed", "c3": "completed"}
        assert [(c[1], c[2]) for c in calls] == [("c1", "INTERRUPTED"), ("c2", "INTERRUPTED")]
        assert all(c[3] == "crypto_download" for c in calls)


class TestBacktestCompensation:
    def test_marks_stale_failed(self, comp_sessionmaker, monkeypatch):
        from backtest import routes as backtest_routes

        with comp_sessionmaker() as db:
            db.add_all(
                [
                    BacktestTask(id="b1", strategy_name="DualMA", backtest_config="{}", status="pending"),
                    BacktestTask(id="b2", strategy_name="DualMA", backtest_config="{}", status="running"),
                    BacktestTask(id="b3", strategy_name="DualMA", backtest_config="{}", status="completed"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, "backtest.routes.notify_task_event")
        monkeypatch.setattr(backtest_routes, "get_db_session", lambda: _fake_db_session(comp_sessionmaker))

        assert backtest_routes.compensate_interrupted_tasks() == 2

        with comp_sessionmaker() as db:
            rows = {r.id: r.status for r in db.query(BacktestTask).all()}
        assert rows == {"b1": "failed", "b2": "failed", "b3": "completed"}
        assert [(c[1], c[2]) for c in calls] == [("b1", "INTERRUPTED"), ("b2", "INTERRUPTED")]
        assert all(c[3] == "DualMA" for c in calls)


class TestResearchCompensation:
    def test_stale_heartbeat_interrupted(self, comp_sessionmaker, monkeypatch):
        from research import loop as research_loop

        now = time.time()
        with comp_sessionmaker() as db:
            db.add_all(
                [
                    ResearchSession(owner_id="u1", name="跑一半", status="running", heartbeat_at=now - 3600),
                    ResearchSession(owner_id="u1", name="活跃中", status="running", heartbeat_at=now),
                    ResearchSession(owner_id="u1", name="已完成", status="completed"),
                    ResearchSession(owner_id="u1", name="排队中", status="pending"),
                ]
            )
            db.commit()

        calls = _patch_notify(monkeypatch, "research.loop.notify_task_event")
        monkeypatch.setattr(research_loop, "get_db_session", lambda: _fake_db_session(comp_sessionmaker))

        assert research_loop.compensate_interrupted_sessions() == 1

        with comp_sessionmaker() as db:
            rows = {r.name: r.status for r in db.query(ResearchSession).all()}
        assert rows == {"跑一半": "failed", "活跃中": "running", "已完成": "completed", "排队中": "pending"}
        assert [(c[1], c[2]) for c in calls] == [("1", "INTERRUPTED")]
        assert calls[0][3] == "跑一半"

    def test_pending_without_heartbeat_untouched(self, comp_sessionmaker, monkeypatch):
        # pending 无心跳线：不误杀（多进程排队中无法区分），只处理 running+过期心跳
        from research import loop as research_loop

        with comp_sessionmaker() as db:
            db.add(ResearchSession(owner_id="u1", name="排队", status="pending"))
            db.commit()

        calls = _patch_notify(monkeypatch, "research.loop.notify_task_event")
        monkeypatch.setattr(research_loop, "get_db_session", lambda: _fake_db_session(comp_sessionmaker))
        assert research_loop.compensate_interrupted_sessions() == 0
        assert calls == []


if __name__ == "__main__":
    raise SystemExit("请用 pytest 运行: uv run pytest tests/unit/notifications/test_compensation.py -v")
