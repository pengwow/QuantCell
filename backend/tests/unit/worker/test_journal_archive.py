"""StrategyManager.archive_journal_files 单元测试。

归档语义：把 live/rl_live 目录下 worker_{id}.jsonl（及 reconcile 报告）move 到
来源目录 archive/ 子目录，下次启动即 fresh start 重锚。报告文件当前无自动写盘方
（Rust reconcile 只返回 dict 不落盘），存在即收是防御性设计。
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from worker import strategy_manager as sm
from worker.strategy_manager import StrategyManager


class _FixedDatetime(datetime):
    """固定 now() 的 datetime 子类，替换 sm.datetime 防秒边界 flaky。"""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


TS = "20260102-030405"


@pytest.fixture
def manager() -> StrategyManager:
    # 绕过 __init__（重装配 + 全局副作用）；archive_journal_files 无实例状态依赖
    return object.__new__(StrategyManager)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "celldata"
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(d))
    return d


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sm, "datetime", _FixedDatetime)


def test_archive_live_journal_and_reconcile(manager, data_dir, fixed_now):
    live = data_dir / "live"
    live.mkdir(parents=True)
    (live / "worker_7.jsonl").write_text('{"t":1}\n', encoding="utf-8")
    (live / "worker_7.reconcile.json").write_text("{}", encoding="utf-8")

    moved = manager.archive_journal_files(7)

    by_src = {Path(m["from"]).name: Path(m["to"]) for m in moved}
    assert set(by_src) == {"worker_7.jsonl", "worker_7.reconcile.json"}
    assert by_src["worker_7.jsonl"] == live / "archive" / f"worker_7.{TS}.jsonl"
    assert by_src["worker_7.reconcile.json"] == live / "archive" / f"worker_7.reconcile.{TS}.json"
    # 文件内容真被移动（旧路径不存在、新路径可读）
    assert not (live / "worker_7.jsonl").exists()
    assert (by_src["worker_7.jsonl"]).read_text(encoding="utf-8") == '{"t":1}\n'


def test_archive_rl_journal_goes_to_rl_archive(manager, data_dir, fixed_now):
    rl = data_dir / "rl_live"
    rl.mkdir(parents=True)
    (rl / "worker_9.jsonl").write_text("rl\n", encoding="utf-8")

    moved = manager.archive_journal_files(9)

    assert len(moved) == 1
    assert Path(moved[0]["to"]) == rl / "archive" / f"worker_9.{TS}.jsonl"


def test_archive_no_candidates_raises_value_error(manager, data_dir, fixed_now):
    with pytest.raises(ValueError, match="无可归档"):
        manager.archive_journal_files(42)


def test_archive_name_conflict_appends_index(manager, data_dir, fixed_now):
    live = data_dir / "live"
    (live / "archive").mkdir(parents=True)
    # 预置同时间戳归档文件，模拟同秒内二次归档
    (live / "archive" / f"worker_3.{TS}.jsonl").write_text("old\n", encoding="utf-8")
    (live / "worker_3.jsonl").write_text("new\n", encoding="utf-8")

    moved = manager.archive_journal_files(3)

    assert Path(moved[0]["to"]) == live / "archive" / f"worker_3.{TS}_1.jsonl"
    assert (live / "archive" / f"worker_3.{TS}.jsonl").read_text(encoding="utf-8") == "old\n"


# ---------- WorkerCoreService.archive_worker_journal ----------
from contextlib import contextmanager
from types import SimpleNamespace

import worker.core_service as cs
from worker.core_service import WorkerCoreService
from worker.exceptions import (
    WorkerException,
    WorkerNotFoundException,
    WorkerOperationException,
    WorkerStateConflictException,
)


class _FakeWorkerSystem:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result if result is not None else [{"from": "a", "to": "b"}]
        self.error = error
        self.calls: list[int] = []

    def archive_journal_files(self, worker_id: int) -> list[dict]:
        self.calls.append(worker_id)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def fake_worker_system(monkeypatch: pytest.MonkeyPatch) -> _FakeWorkerSystem:
    # core_service.archive_worker_journal 内部 from .strategy_manager import worker_system
    # 为运行时查模块属性，monkeypatch sm.worker_system 即可拦住调用而不触发重装配
    fake = _FakeWorkerSystem()
    monkeypatch.setattr(sm, "worker_system", fake)
    return fake


def _db_with_worker(monkeypatch: pytest.MonkeyPatch, worker_status: str | None) -> None:
    """替换 get_db 与 crud.get_worker，绕开真实 DB（单例 service 便于直测）。"""

    @contextmanager
    def _fake_session():
        yield None

    def _fake_get_worker(db, worker_id):
        if worker_status is None:
            return None
        return SimpleNamespace(id=worker_id, status=worker_status, name=f"worker-{worker_id}")

    monkeypatch.setattr(WorkerCoreService, "get_db", lambda self: _fake_session())
    monkeypatch.setattr(cs.crud, "get_worker", _fake_get_worker)


def test_service_archive_requires_stopped_or_error(monkeypatch, fake_worker_system):
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "running")
    with pytest.raises(WorkerStateConflictException) as exc_info:
        service.archive_worker_journal(1)
    assert exc_info.value.code == 409
    assert not fake_worker_system.calls


def test_service_archive_worker_not_found(monkeypatch, fake_worker_system):
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, None)
    with pytest.raises(WorkerNotFoundException):
        service.archive_worker_journal(999)
    assert not fake_worker_system.calls


def test_service_archive_success_returns_contract(monkeypatch, fake_worker_system):
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "stopped")
    # WorkerCoreService 是模块级轻量单例，archive_journal_files 无真实文件依赖
    # （QUANTCELL_DATA_DIR 未注入时 live 下无 worker_1 文件，fake 拦截不触盘）
    result = service.archive_worker_journal(1)
    assert result["worker_id"] == 1
    assert result["archived"] == [{"from": "a", "to": "b"}]
    assert "fresh start" in result["hint"]
    assert fake_worker_system.calls == [1]


def test_service_archive_no_candidates_maps_to_operation_error(monkeypatch):
    fake = _FakeWorkerSystem(error=ValueError("worker 5 无可归档的 journal 文件"))
    monkeypatch.setattr(sm, "worker_system", fake)
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "stopped")
    with pytest.raises(WorkerOperationException):
        service.archive_worker_journal(5)


def test_service_archive_move_failure_maps_to_500(monkeypatch):
    fake = _FakeWorkerSystem(error=RuntimeError("移动失败"))
    monkeypatch.setattr(sm, "worker_system", fake)
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "error")
    with pytest.raises(WorkerException) as exc_info:
        service.archive_worker_journal(6)
    assert exc_info.value.code == 500
