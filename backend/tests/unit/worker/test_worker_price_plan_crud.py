"""固化计划存取单测：只测 crud 口径，存储实现细节（config 键位）不进断言"""

import uuid

import pytest

from utils.db_session import get_db_session
from worker import crud

PLAN = {
    "levels": [{"index": 0, "price": 100.0, "action": "buy", "target_position": 0.1, "label": "入场"}],
    "summary": {"price_min": 100.0, "price_max": 100.0, "entry_price": 100.0, "extra": {}},
    "warnings": [],
}


@pytest.fixture
def db():
    """与 crud 自持会话同源的会话（DB_FILE 临时库），保证读写在同一个库发生"""
    with get_db_session() as session:
        yield session


@pytest.fixture
def worker_row(db):
    from worker import schemas

    return crud.create_worker(
        db,
        schemas.WorkerCreate(
            name=f"price-plan-{uuid.uuid4().hex[:8]}",
            strategy_name="grid",
            trading_config=schemas.TradingConfig(),
        ),
    )


def test_save_fixed_then_read(db, worker_row):
    crud.save_worker_price_plan(str(worker_row.id), PLAN, ref_price=100.0)
    stored = crud.get_worker_price_plan(str(worker_row.id))
    assert stored["state"] == "fixed"
    assert stored["ref_price"] == 100.0
    assert stored["plan"]["levels"][0]["price"] == 100.0


def test_save_pending_placeholder(db, worker_row):
    crud.save_worker_price_plan(str(worker_row.id), None, ref_price=None)
    stored = crud.get_worker_price_plan(str(worker_row.id))
    assert stored["state"] == "pending" and stored["plan"] is None


def test_missing_worker_returns_none(db):
    assert crud.get_worker_price_plan("no-such-worker") is None
