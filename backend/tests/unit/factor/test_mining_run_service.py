"""MiningRunService：建行、终态落库、懒修正、删除约束。"""

import json

import pytest

from factor.job_manager import JobStatus
from factor.mining_run_service import MiningRunError, MiningRunService
from factor.models import FactorMiningRun


@pytest.fixture
def svc():
    return MiningRunService()


PARAMS = {"instruments": ["BTCUSDT"], "interval": "1h", "n_rounds": 2, "n_candidates": 4}
RESULT = {
    "candidates": [],
    "best": [],
    "composite": None,
    "stats": {
        "generated": 3,
        "unique": 2,
        "succeeded": 1,
        "failed": 2,
        "redundant": 0,
        "rounds": 1,
        "symbols": ["BTCUSDT"],
        "interval": "1h",
        "model_name": "m",
    },
}


def test_create_running(db_session, svc):
    row = svc.create_running(db_session, "job-1", PARAMS)
    assert row.status == "running"
    assert json.loads(row.params_json)["interval"] == "1h"


def test_mark_completed_persists_result_and_stats(db_session, svc):
    svc.create_running(db_session, "job-1", PARAMS)
    svc.mark_completed(db_session, "job-1", RESULT)
    row = db_session.query(FactorMiningRun).filter_by(job_id="job-1").one()
    assert row.status == "completed" and row.finished_at is not None
    assert json.loads(row.result_json)["stats"]["succeeded"] == 1
    assert json.loads(row.stats_json)["generated"] == 3


def test_mark_failed_persists_error(db_session, svc):
    svc.create_running(db_session, "job-1", PARAMS)
    svc.mark_failed(db_session, "job-1", "boom")
    row = db_session.query(FactorMiningRun).filter_by(job_id="job-1").one()
    assert row.status == "failed" and row.error == "boom" and row.finished_at is not None
