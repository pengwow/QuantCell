"""/workers/{id}/plan 路由冒烟：pending / fixed / 重启复读（spec §5.4）"""

import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from utils.db_session import get_db_session
from worker import crud as worker_crud

client = TestClient(app)


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """worker 路由带统一认证（P0 加固后无匿名放行）；本文件只测 plan 语义，
    借 utils.auth 的 debug 豁免（每次请求实时读 env）关掉校验"""
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture
def db():
    """路由内 crud 自持会话同源（DB_FILE 临时库）；tests/unit/api 无 conftest，就地声明"""
    with get_db_session() as session:
        yield session


@pytest.fixture
def worker_row(db):
    from worker import schemas

    return worker_crud.create_worker(
        db,
        schemas.WorkerCreate(
            name=f"price-plan-api-{uuid.uuid4().hex[:8]}",
            strategy_name="grid",
            trading_config=schemas.TradingConfig(),
        ),
    )


def test_plan_pending_when_no_row(db, worker_row):
    r = client.get(f"/api/v1/workers/{worker_row.id}/plan")
    assert r.status_code == 200
    assert r.json()["data"]["state"] == "pending"


def test_plan_fixed_with_runtime(db, worker_row):
    worker_crud.save_worker_price_plan(
        str(worker_row.id),
        {
            "levels": [{"index": 0, "price": 100.0, "action": "buy", "target_position": 0.1, "label": "入场"}],
            "summary": {"price_min": 100.0, "price_max": 100.0, "entry_price": 100.0, "extra": {}},
            "warnings": [],
        },
        100.0,
    )
    r = client.get(f"/api/v1/workers/{worker_row.id}/plan")
    data = r.json()["data"]
    assert data["state"] == "fixed"
    assert data["plan"]["levels"][0]["price"] == 100.0
    assert "triggered_count" in data and "next_trigger" in data and "triggered_indexes" in data


def test_fixed_plan_reread_from_db(db, worker_row):
    """spec §5.4：固化计划以 DB 为事实源，重启路径（重新全量读库）后仍可复读"""
    plan = {
        "levels": [{"index": 0, "price": 100.0, "action": "buy", "target_position": 0.1, "label": "入场"}],
        "summary": {"price_min": 100.0, "price_max": 100.0, "entry_price": 100.0, "extra": {}},
        "warnings": [],
    }
    worker_crud.save_worker_price_plan(str(worker_row.id), plan, 100.0)
    first = worker_crud.get_worker_price_plan(str(worker_row.id))
    again = worker_crud.get_worker_price_plan(str(worker_row.id))
    assert again == first
    assert again["ref_price"] == 100.0 and again["plan"]["levels"][0]["price"] == 100.0
