"""回测协作式停止（stop_control + BacktestService 接线）行为校验。

锁住四件事：
1. 注册表生命周期：register 覆盖旧令牌、cancel 置位、pop 清理
2. stop_backtest 对运行中任务：状态落盘 stopped + 执行线程令牌置位
3. 竞态防护：跑到终点前一刻 stop，completed 不得覆盖 stopped
4. 品种边界取消：engine 抛 BacktestCancelled 后 run_backtest 返回 stopped
   且注册表条目已清理
"""

import json
import threading

import pytest

from backtest import stop_control
from backtest.service import BacktestService


@pytest.fixture(autouse=True)
def _reset_stop_registry():
    """注册表是模块级全局：每个用例前后清空，避免跨用例串扰"""
    stop_control._EVENTS.clear()
    stop_control._CANCELLED_BEFORE_RUN.clear()
    yield
    stop_control._EVENTS.clear()
    stop_control._CANCELLED_BEFORE_RUN.clear()


def _make_service(tmp_path) -> BacktestService:
    svc = BacktestService()
    svc.results_dir = tmp_path / "backtest_results"
    svc.results_dir.mkdir(parents=True, exist_ok=True)
    return svc


def _write_task(svc: BacktestService, task_id: str, status: str) -> None:
    tasks_dir = svc.results_dir.parent / "backtest_tasks"
    tasks_dir.mkdir(exist_ok=True)
    task = {
        "id": task_id,
        "strategy_name": "dual_ma",
        "symbols": ["BTCUSDT"],
        "timeframes": ["1h"],
        "status": status,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    (tasks_dir / f"task_{task_id}.json").write_text(json.dumps(task), encoding="utf-8")


def _read_task_status(svc: BacktestService, task_id: str) -> str:
    tasks_dir = svc.results_dir.parent / "backtest_tasks"
    task = json.loads((tasks_dir / f"task_{task_id}.json").read_text(encoding="utf-8"))
    return task["status"]


def test_stop_control_lifecycle() -> None:
    event = stop_control.register("t1")
    assert not event.is_set()
    # 覆盖语义：重复 register 返回全新令牌，旧令牌的置位不会串到新任务
    event.set()
    fresh = stop_control.register("t1")
    assert not fresh.is_set()
    assert stop_control.cancel("t1") is True
    assert fresh.is_set()
    # 未注册任务 cancel 返回 False；pop 后再 cancel 也不报错
    assert stop_control.cancel("missing") is False
    stop_control.pop("t1")
    assert stop_control.cancel("t1") is False


@pytest.fixture()
def _patch_engine_cls(monkeypatch):
    """把 service.run_backtest 延迟 import 的引擎类替换为注入行为的假实现"""

    def _install(engine_run):
        class _FakeEngine:
            def __init__(self, data_provider):
                pass

            # service 以实例方法调用 run_backtest，engine_run 需接收 self
            run_backtest = engine_run

        monkeypatch.setattr(
            "backtest.engine_service.EventDrivenBacktestService", _FakeEngine
        )

    return _install


def test_stop_backtest_writes_status_and_sets_token(tmp_path, _patch_engine_cls) -> None:
    svc = _make_service(tmp_path)
    task_id = "stop-token-1"
    _write_task(svc, task_id, "running")

    # 在执行线程视角注册令牌，stop_backtest 应置位它（跨线程同 dict）
    event = stop_control.register(task_id)

    result = svc.stop_backtest(task_id)

    assert result["status"] == "success"
    assert event.is_set()
    assert _read_task_status(svc, task_id) == "stopped"
    stop_control.pop(task_id)


def test_completed_not_written_when_stop_requested(tmp_path, _patch_engine_cls) -> None:
    svc = _make_service(tmp_path)
    task_id = "stop-race-1"
    _write_task(svc, task_id, "running")

    raw_result = {"portfolio": {"metrics": [{"key": "total_return", "value": 1.5}]}}

    def _run(self, **kwargs):
        # 模拟 stop 端点在执行期间到达：写 stopped 状态 + 置位取消令牌，
        # 随后 engine 正常返回结果
        kwargs["stop_event"].set()
        svc._update_task_status(task_id, "stopped")
        return raw_result

    _patch_engine_cls(_run)
    svc.run_backtest(task_id)

    # 关键断言：任务状态保持 stopped，不被 completed 覆盖
    assert _read_task_status(svc, task_id) == "stopped"
    assert stop_control.cancel(task_id) is False  # 注册表已 pop


def test_cancelled_returns_stopped_and_cleans_registry(tmp_path, _patch_engine_cls) -> None:
    svc = _make_service(tmp_path)
    task_id = "stop-cancel-1"
    _write_task(svc, task_id, "running")

    def _run(self, **kwargs):
        # 模拟：品种边界检查到停止令牌，提前退出
        kwargs["stop_event"].set()
        raise stop_control.BacktestCancelled("停止令牌已置位")

    _patch_engine_cls(_run)
    result = svc.run_backtest(task_id)

    assert result["status"] == "stopped"
    assert _read_task_status(svc, task_id) == "stopped"
    assert stop_control.cancel(task_id) is False  # 注册表已 pop
