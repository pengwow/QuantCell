"""采集/回测/研究三域终态挂钩单测。

三域有自己的任务表（不写 async_task_records 影子行），挂钩只做
「内部状态 → task_notices 终态」映射转发。统一 monkeypatch 各模块
命名空间里的 notify_task_event 收集调用断言，不触发任何业务库写入；
inspect.getsource 接线检查确保挂钩真的被终态收口函数调用。
"""

import inspect
import re

from backtest import routes as backtest_routes
from collector.utils import task_manager
from research import loop as research_loop


def _collect_calls(monkeypatch, target: str):
    calls = []

    def fake(task_type, task_id, status, *, name=None, error=None, extra=None):
        calls.append((task_type, task_id, status, name, error))

    monkeypatch.setattr(target, fake)
    return calls


# ---------- collector ----------


class TestCollectorHook:
    def test_complete_succeeded(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "collector.utils.task_manager.notify_task_event")
        task_manager._notify_terminal("t-1", task_manager.TASK_STATUS_SUCCEEDED, name="crypto_download")
        assert calls == [("collector_task", "t-1", "SUCCEEDED", "crypto_download", None)]

    def test_failed_with_error(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "collector.utils.task_manager.notify_task_event")
        task_manager._notify_terminal("t-2", task_manager.TASK_STATUS_FAILED, name="crypto_download", error="超时")
        assert calls == [("collector_task", "t-2", "FAILED", "crypto_download", "超时")]

    def test_wired_into_terminal_exits(self):
        # complete_task / fail_task 是采集任务唯一的两个终态收口，都必须调挂钩
        assert "_notify_terminal" in inspect.getsource(task_manager.TaskManager.complete_task)
        assert "_notify_terminal" in inspect.getsource(task_manager.TaskManager.fail_task)


# ---------- backtest ----------


class TestBacktestHook:
    def test_success_status_maps_succeeded(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "backtest.routes.notify_task_event")
        backtest_routes.notify_backtest_result("b-1", {"status": "success"}, name="DualMA")
        backtest_routes.notify_backtest_result("b-2", {"status": "completed"}, name="DualMA")
        assert calls == [
            ("backtest", "b-1", "SUCCEEDED", "DualMA", None),
            ("backtest", "b-2", "SUCCEEDED", "DualMA", None),
        ]

    def test_stopped_is_silent(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "backtest.routes.notify_task_event")
        backtest_routes.notify_backtest_result("b-3", {"status": "stopped", "message": "用户终止"}, name="DualMA")
        assert calls == []

    def test_other_status_maps_failed(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "backtest.routes.notify_task_event")
        backtest_routes.notify_backtest_result("b-4", {"status": "error", "message": "代理不可用"}, name="DualMA")
        backtest_routes.notify_backtest_result("b-5", {"status": None}, name="DualMA")
        assert calls == [
            ("backtest", "b-4", "FAILED", "DualMA", "代理不可用"),
            ("backtest", "b-5", "FAILED", "DualMA", "回测失败"),
        ]

    def test_wired_into_run_backtest_async(self):
        # run_backtest_async 是闭包拿不到引用，对整个 routes 源码做接线检查。
        # 用正则而非字面缩进匹配：源码缩进会随后续重构/格式化变化，
        # 断言语义只是「notify_task_event 以 'backtest' 为首个实参被调用」
        src = inspect.getsource(backtest_routes)
        assert "notify_backtest_result(task_id, result" in src
        assert re.search(r'notify_task_event\(\s*"backtest"', src)


# ---------- research ----------


class TestResearchHook:
    def test_completed_maps_succeeded(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "research.loop.notify_task_event")
        research_loop._notify_session_terminal(7, "主力因子挖掘", "completed")
        assert calls == [("research", "7", "SUCCEEDED", "主力因子挖掘", None)]

    def test_failed_maps_failed_with_error(self, monkeypatch):
        calls = _collect_calls(monkeypatch, "research.loop.notify_task_event")
        research_loop._notify_session_terminal(8, "主力因子挖掘", "failed", error="LLM 超时")
        assert calls == [("research", "8", "FAILED", "主力因子挖掘", "LLM 超时")]

    def test_cancelled_is_silent(self, monkeypatch):
        # cancel/pause 是用户主动操作，无信息增量（spec §4）
        calls = _collect_calls(monkeypatch, "research.loop.notify_task_event")
        research_loop._notify_session_terminal(9, "主力因子挖掘", "cancelled")
        assert calls == []

    def test_wired_into_finish(self):
        assert "_notify_session_terminal" in inspect.getsource(research_loop.ResearchLoop._finish)


if __name__ == "__main__":
    raise SystemExit("请用 pytest 运行: uv run pytest tests/unit/notifications/test_domain_hooks.py -v")
