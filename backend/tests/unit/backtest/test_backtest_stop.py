"""回测协作式停止（stop_control + BacktestService 接线）行为校验。

锁住六件事：
1. 注册表生命周期：register 覆盖旧令牌、cancel 置位、pop 清理
2. stop_backtest 对运行中任务：状态落盘 stopped + 执行线程令牌置位
3. 终止确认：执行线程退出后 cancel_and_wait 得到确认，stop 反馈 success
4. 超时强制终止：线程迟迟不退出，stop 超时返回 forced（任务仍被标记 stopped，
   且进度记录同步置 stopped——否则 /progress 一直返回 running，前端轮询
   收不到终止信号，进度条会永远更新下去）
5. stop 先于任务开跑：取消意图在 register 时兑现，线程随即退出，反馈 success
6. 竞态防护：跑到终点前一刻 stop，completed 不得覆盖 stopped
"""

import json
import threading
import time

import pytest

from backtest import stop_control
from backtest.progress_tracker import StageStatus, get_progress_tracker
from backtest.service import BacktestService


@pytest.fixture(autouse=True)
def _reset_stop_registry():
    """注册表是模块级全局：每个用例前后清空，避免跨用例串扰"""
    stop_control._EVENTS.clear()
    stop_control._CANCELLED_BEFORE_RUN.clear()
    stop_control._EXIT_SIGNALS.clear()
    yield
    stop_control._EVENTS.clear()
    stop_control._CANCELLED_BEFORE_RUN.clear()
    stop_control._EXIT_SIGNALS.clear()


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

        monkeypatch.setattr("backtest.engine_service.EventDrivenBacktestService", _FakeEngine)

    return _install


def test_stop_confirmed_when_thread_exits(tmp_path) -> None:
    """执行线程走到 finally（notify_exit）后，stop 反馈终止成功"""
    svc = _make_service(tmp_path)
    task_id = "stop-confirm-1"
    _write_task(svc, task_id, "running")

    event = stop_control.register(task_id)

    # 模拟执行线程：品种边界感知取消 → run_backtest finally 顺序 notify_exit → pop
    def _executor():
        time.sleep(0.1)
        stop_control.notify_exit(task_id)
        stop_control.pop(task_id)

    threading.Thread(target=_executor, daemon=True).start()

    result = svc.stop_backtest(task_id, confirm_timeout=5.0)

    assert result["status"] == "success"
    assert event.is_set()
    assert _read_task_status(svc, task_id) == "stopped"


def test_stop_forced_on_confirm_timeout(tmp_path) -> None:
    """单品种阻塞段无法中断：等待超时后返回 forced，任务仍被标记 stopped 且令牌已置位"""
    svc = _make_service(tmp_path)
    task_id = "stop-forced-1"
    _write_task(svc, task_id, "running")

    # 执行线程已开跑并注册令牌，但卡在单品种回测里不退出
    event = stop_control.register(task_id)

    # 模拟 /run 已创建的进度记录（前端轮询 /progress 的数据源）
    tracker = get_progress_tracker()
    tracker.create_progress(task_id)
    try:
        result = svc.stop_backtest(task_id, confirm_timeout=0.2)

        assert result["status"] == "forced"
        assert event.is_set()  # 取消令牌已投递，线程将在下一品种边界自动退出
        assert _read_task_status(svc, task_id) == "stopped"
        # 进度记录与任务表必须同步置终态
        assert tracker.get_progress(task_id).status == StageStatus.STOPPED
    finally:
        # 进度记录是全局单例，用例内自产自销避免串扰
        tracker._progresses.pop(task_id, None)
        stop_control.pop(task_id)


def test_stop_before_run_arrives_at_register(tmp_path) -> None:
    """对 pending 任务先 stop：取消意图在 register 时兑现，线程随即退出 → 终止成功"""
    svc = _make_service(tmp_path)
    task_id = "stop-pending-1"
    _write_task(svc, task_id, "pending")

    # 模拟执行线程晚于 stop 端点开跑
    def _executor():
        time.sleep(0.1)
        register_event = stop_control.register(task_id)
        # 令牌意图兑现：register 返回的令牌应是已置位的
        assert register_event.is_set()
        stop_control.notify_exit(task_id)
        stop_control.pop(task_id)

    threading.Thread(target=_executor, daemon=True).start()

    result = svc.stop_backtest(task_id, confirm_timeout=5.0)

    assert result["status"] == "success"
    assert _read_task_status(svc, task_id) == "stopped"


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
