"""submit 的 on_terminal 回调：同一工作线程在终态统一回调，且不传回调时行为不变。"""

import time

import pytest

from factor.job_manager import FactorJobManager


@pytest.fixture
def mgr():
    m = FactorJobManager(sweep_interval=9999)
    yield m
    m.shutdown()


def _wait(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met before timeout")


def test_on_terminal_success_callback(mgr):
    calls = []
    jid = mgr.submit(
        "llm_mine",
        {},
        lambda p, s, e=None: {"ok": True},
        on_terminal=lambda job_id, ok, payload: calls.append((job_id, ok, payload)),
    )
    _wait(lambda: calls)
    assert calls == [(jid, True, {"ok": True})]


def test_on_terminal_failure_callback(mgr):
    def boom(p, s, _e=None):
        raise RuntimeError("kaboom")

    calls = []
    jid = mgr.submit("llm_mine", {}, boom, on_terminal=lambda job_id, ok, payload: calls.append((job_id, ok, payload)))
    _wait(lambda: calls)
    assert len(calls) == 1
    assert calls[0][0] == jid and calls[0][1] is False
    assert "kaboom" in calls[0][2]


def test_no_callback_still_terminal(mgr):
    # analyze/compare 不传 on_terminal：任务正常终态，不报错
    jid = mgr.submit("analyze", {}, lambda p, s, e=None: 1)
    _wait(lambda: mgr.get(jid) and mgr.get(jid).status.value == "completed")


def test_append_event_accumulates_and_queries(mgr):
    jid = mgr.submit("llm_mine", {}, lambda p, s, e=None: 1)
    _wait(lambda: mgr.get(jid).status.value == "completed")

    e0 = mgr.append_event(jid, "info", "generating", 10.0, "第一条")
    e1 = mgr.append_event(jid, "info", "evaluating", 20.0, "第二条")
    assert e0["idx"] == 0 and e1["idx"] == 1
    page = mgr.get_events(jid, after_idx=0)
    assert [e["idx"] for e in page["events"]] == [0, 1]
    assert page["next_idx"] == 2
    # after_idx 增量
    page1 = mgr.get_events(jid, after_idx=1)
    assert [e["idx"] for e in page1["events"]] == [1]
    # 任务已 completed（progress=100）：事件携带的小 p 取 max，不回退进度
    assert mgr.get(jid).progress == 100.0


def test_append_event_fifo_cap_500(mgr):
    jid = mgr.submit("llm_mine", {}, lambda p, s, e=None: 1)
    _wait(lambda: mgr.get(jid).status.value == "completed")
    for i in range(505):
        mgr.append_event(jid, "info", "generating", None, f"e{i}")
    page = mgr.get_events(jid, after_idx=0)
    events = page["events"]
    assert len(events) == 500
    # 保留最新 500 条，idx 仍全局单调
    assert events[0]["msg"] == "e5" and events[-1]["msg"] == "e504"
    assert page["next_idx"] == 505


def test_get_events_unknown_job_is_none(mgr):
    assert mgr.get_events("nope") is None


def test_on_event_cb_receives_job_id(mgr):
    got = []

    def runner(on_progress, _on_stage, on_event=None):
        on_event("info", "generating", 5.0, "hi")
        return {"ok": True}

    jid = mgr.submit(
        "llm_mine",
        {},
        runner,
        on_event_cb=lambda job_id, level, stage, p, msg: got.append((job_id, level, stage, p, msg)),
    )
    _wait(lambda: got)
    assert got == [(jid, "info", "generating", 5.0, "hi")]
