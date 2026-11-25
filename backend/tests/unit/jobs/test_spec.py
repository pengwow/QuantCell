"""JobSpec / JobResult 契约：可 JSON 往返，且拒绝携带父子进程不可共享的对象。"""

import pytest

from jobs.spec import JobResult, JobSpec


def test_spec_roundtrip_keeps_payload_and_resources():
    spec = JobSpec(
        job_id="job-1",
        kind="backtest",
        payload={"symbols": ["BTC/USDT"], "config": {"start": "2024-01-01", "leverage": 3}},
        resources={"cores": 2},
    )

    restored = JobSpec.from_json(spec.to_json())

    assert restored == spec
    assert restored.cores == 2


def test_spec_rejects_non_json_payload():
    # 闭包 / 数据库 Session 这类对象必须在构造期就被挡住，不能带进进程池
    with pytest.raises(TypeError, match="不可序列化"):
        JobSpec(job_id="job-1", kind="backtest", payload={"handler": lambda: None})


def test_spec_rejects_empty_identity():
    with pytest.raises(ValueError, match="job_id"):
        JobSpec(job_id="", kind="backtest")
    with pytest.raises(ValueError, match="kind"):
        JobSpec(job_id="job-1", kind="")


def test_spec_rejects_invalid_cores():
    with pytest.raises(ValueError, match="cores"):
        _ = JobSpec(job_id="job-1", kind="backtest", resources={"cores": 0}).cores


def test_result_roundtrip_and_status_validation():
    result = JobResult(status="succeeded", result_ref="/tmp/result.json", metrics={"wall_seconds": 1.5})

    assert JobResult.from_dict(result.to_dict()) == result

    with pytest.raises(ValueError, match="非法作业终态"):
        JobResult(status="done")
