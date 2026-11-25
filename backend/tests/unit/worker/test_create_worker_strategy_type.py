"""worker.strategy_type 回填：create_worker 镜像被引用策略行的类型。

背景：worker 表有 strategy_type 列（rule/rl），但 WorkerCreate 不接收该字段
（worker 镜像策略行）。/workers/{id}/lifecycle/optimize 按该列分支，不回填会
让 RL 策略的 worker 走成 rule 分支（worker/routes.py:1373）。
"""

import pytest

from strategy.models import Strategy
from worker import crud, schemas


def _worker_payload(**overrides):
    payload = {
        "name": "strategy-type-test",
        "trading_config": {
            "exchange": "binance",
            "symbols_config": {"type": "symbols", "symbols": ["BTCUSDT"]},
            "interval": "1h",
            "market_type": "futures",
            "trading_mode": "paper",
        },
    }
    payload.update(overrides)
    return payload


def _strategy(db_session, name: str, strategy_type: str) -> Strategy:
    row = Strategy(name=name, strategy_type=strategy_type, parameters="{}")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.mark.parametrize("strategy_type", ["rl", "rule"])
def test_create_worker_mirrors_strategy_type(db_session, strategy_type):
    strategy = _strategy(db_session, f"mirror-{strategy_type}", strategy_type)

    worker = crud.create_worker(
        db_session,
        schemas.WorkerCreate(**_worker_payload(strategy_id=strategy.id, strategy_name=strategy.name)),
    )

    assert worker.strategy_type == strategy_type
    assert worker.to_dict()["strategy_info"]["strategy_type"] == strategy_type


def test_create_worker_without_strategy_falls_back_to_rule(db_session):
    worker = crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload()))
    assert worker.strategy_type == "rule"


def test_create_worker_missing_strategy_row_falls_back_to_rule(db_session):
    worker = crud.create_worker(db_session, schemas.WorkerCreate(**_worker_payload(strategy_id=999_999)))
    assert worker.strategy_type == "rule"
