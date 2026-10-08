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
        lambda p, s: {"ok": True},
        on_terminal=lambda job_id, ok, payload: calls.append((job_id, ok, payload)),
    )
    _wait(lambda: calls)
    assert calls == [(jid, True, {"ok": True})]


def test_on_terminal_failure_callback(mgr):
    def boom(p, s):
        raise RuntimeError("kaboom")

    calls = []
    jid = mgr.submit("llm_mine", {}, boom, on_terminal=lambda job_id, ok, payload: calls.append((job_id, ok, payload)))
    _wait(lambda: calls)
    assert len(calls) == 1
    assert calls[0][0] == jid and calls[0][1] is False
    assert "kaboom" in calls[0][2]


def test_no_callback_still_terminal(mgr):
    # analyze/compare 不传 on_terminal：任务正常终态，不报错
    jid = mgr.submit("analyze", {}, lambda p, s: 1)
    _wait(lambda: mgr.get(jid) and mgr.get(jid).status.value == "completed")
