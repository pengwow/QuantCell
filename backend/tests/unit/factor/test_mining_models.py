"""factor_mining_runs 表模型冒烟测试。"""

from factor.models import FactorMiningRun


def test_mining_run_defaults():
    row = FactorMiningRun(job_id="job-1", status="running", params_json='{"interval": "1h"}')
    assert row.status == "running"
    assert row.result_json is None
    assert row.stats_json is None
    assert row.error is None
    assert row.finished_at is None
