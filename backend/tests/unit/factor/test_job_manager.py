"""FactorJobManager 单测：状态流转/并发/TTL/WS 桥接。"""

import time

from factor.job_manager import FactorJobManager, JobStatus


def make_manager(ttl=1800.0, sweep=300.0, max_workers=4):
    return FactorJobManager(ttl_seconds=ttl, sweep_interval=sweep, max_workers=max_workers)


def wait_terminal(mgr, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = mgr.get(job_id)
        if job is not None and job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} 未在 {timeout}s 内到终态")


def test_submit_success_completes_with_result(tmp_path):
    mgr = make_manager()

    def runner(on_progress, on_stage, _on_event=None):
        on_progress(30, "data", "读取")
        on_progress(90, "computing", "计算")
        return {"ok": True}

    jid = mgr.submit("analyze", {}, runner)
    job = wait_terminal(mgr, jid)
    assert job.status == JobStatus.COMPLETED
    assert job.progress == 100.0
    assert mgr.get_result(jid) == {"ok": True}
    status = mgr.get_status(jid)
    assert "result" not in status


def test_submit_failure_records_error(tmp_path):
    mgr = make_manager()

    def runner(on_progress, on_stage, _on_event=None):
        raise ValueError("因子不存在: ghost")

    jid = mgr.submit("analyze", {}, runner)
    job = wait_terminal(mgr, jid)
    assert job.status == JobStatus.FAILED
    assert "ghost" in job.error
    assert mgr.get_result(jid) is None


def test_progress_reaches_completion(tmp_path):
    mgr = make_manager()

    def runner(on_progress, on_stage, _on_event=None):
        for i in range(3):
            on_progress(30 + i * 20, "computing", f"f{i} ({i + 1}/3)")
        return {}

    jid = mgr.submit("compare", {}, runner)
    assert wait_terminal(mgr, jid).progress == 100.0
    assert mgr.get_status(jid)["progress"] == 100.0


def test_concurrent_jobs_isolated(tmp_path):
    mgr = make_manager()

    def make_runner(v):
        def runner(on_progress, on_stage, _on_event=None):
            time.sleep(0.05)
            return {"v": v}

        return runner

    ids = [mgr.submit("analyze", {}, make_runner(i)) for i in range(4)]
    for i, jid in enumerate(ids):
        assert wait_terminal(mgr, jid).status == JobStatus.COMPLETED
        assert mgr.get_result(jid) == {"v": i}


def test_ttl_cleans_completed_jobs(tmp_path):
    mgr = make_manager(ttl=0.05, sweep=0.05)
    jid = mgr.submit("analyze", {}, lambda p, s, e=None: {})
    wait_terminal(mgr, jid)
    deadline = time.time() + 3.0
    while time.time() < deadline and mgr.get(jid) is not None:
        time.sleep(0.05)
    assert mgr.get(jid) is None


def test_ws_emission_without_result_and_failure_isolated(tmp_path, monkeypatch):
    import factor.job_manager as jm

    calls = []

    class FakeManager:
        def __init__(self):
            self.message_queue = object()  # 非 None 即视为已启动

        async def queue_message(self, message, topic=None):
            calls.append((message, topic))

    fake = FakeManager()
    monkeypatch.setattr(jm, "manager", fake)

    mgr = make_manager()

    def ok(p, s, _on_event=None):
        return {"big": "payload"}

    jid = mgr.submit("analyze", {}, ok)
    wait_terminal(mgr, jid)
    # 给跨线程 emit 一点落袋时间
    deadline = time.time() + 2.0
    while time.time() < deadline and not calls:
        time.sleep(0.02)
    assert calls
    for message, topic in calls:
        assert topic == "factor:job"
        assert message["type"] == "factor:job"
        assert message["data"]["job_id"] == jid
        assert "result" not in message["data"]
    # 至少有一条 completed
    assert any(c[0]["data"]["status"] == "completed" for c in calls)


def test_ws_failure_does_not_break_job(tmp_path, monkeypatch):
    import factor.job_manager as jm

    class BrokenManager:
        message_queue = object()

        async def queue_message(self, *a, **k):
            raise RuntimeError("ws down")

    monkeypatch.setattr(jm, "manager", BrokenManager())
    mgr = make_manager()
    jid = mgr.submit("analyze", {}, lambda p, s, e=None: {"x": 1})
    assert wait_terminal(mgr, jid).status == JobStatus.COMPLETED
