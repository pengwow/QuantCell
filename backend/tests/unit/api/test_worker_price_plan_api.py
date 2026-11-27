"""/workers/{id}/plan 路由冒烟：pending / fixed / 重启复读 / symbol 过滤（spec §5.4 + §4）"""

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
            trading_config=schemas.TradingConfig(symbols_config=schemas.SymbolsConfig(symbols=["BTCUSDT", "ETHUSDT"])),
        ),
    )


def _plan(entry_price: float) -> dict:
    return {
        "levels": [{"index": 0, "price": entry_price, "action": "buy", "target_position": 0.1, "label": "入场"}],
        "summary": {
            "price_min": entry_price,
            "price_max": entry_price,
            "entry_price": entry_price,
            "extra": {},
        },
        "warnings": [],
    }


def test_plan_pending_when_no_row(db, worker_row):
    r = client.get(f"/api/v1/workers/{worker_row.id}/plan")
    assert r.status_code == 200
    assert r.json()["data"]["state"] == "pending"


def test_plan_fixed_with_runtime(db, worker_row):
    worker_crud.save_worker_price_plans(
        str(worker_row.id),
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "state": "fixed",
                "ref_price": 100.0,
                "plan": _plan(100.0),
                "fixed_at": "2026-11-27T00:00:00.000000000+00:00",
            },
            "ETHUSDT": None,
        },
    )
    r = client.get(f"/api/v1/workers/{worker_row.id}/plan")
    data = r.json()["data"]
    assert data["state"] == "fixed"
    assert data["plan"]["levels"][0]["price"] == 100.0
    assert "triggered_count" in data and "next_trigger" in data and "triggered_indexes" in data


def test_plan_symbol_query_filters_entry(db, worker_row):
    """spec §4.8-1：?symbol=ETHUSDT 返回该标的固化 entry；不存在标的 → pending"""
    worker_crud.save_worker_price_plans(
        str(worker_row.id),
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "state": "fixed",
                "ref_price": 100.0,
                "plan": _plan(100.0),
                "fixed_at": "2026-11-27T00:00:00.000000000+00:00",
            },
            "ETHUSDT": {
                "symbol": "ETHUSDT",
                "state": "fixed",
                "ref_price": 2000.0,
                "plan": _plan(2000.0),
                "fixed_at": "2026-11-27T00:00:00.000000000+00:00",
            },
        },
    )
    r = client.get(f"/api/v1/workers/{worker_row.id}/plan", params={"symbol": "ETHUSDT"})
    data = r.json()["data"]
    assert data["state"] == "fixed"
    assert data["plan"]["summary"]["entry_price"] == 2000.0

    r_missing = client.get(f"/api/v1/workers/{worker_row.id}/plan", params={"symbol": "LTCUSDT"})
    assert r_missing.json()["data"]["state"] == "pending"


def test_plan_response_includes_symbols_states(db, worker_row):
    """spec §4.8-2：响应带 symbols: [{"symbol","state"}]，长度=2、顺序=存储顺序"""
    worker_crud.save_worker_price_plans(
        str(worker_row.id),
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "state": "fixed",
                "ref_price": 100.0,
                "plan": _plan(100.0),
                "fixed_at": "2026-11-27T00:00:00.000000000+00:00",
            },
            "ETHUSDT": None,  # pending 占位也进 symbols 表
        },
    )
    r = client.get(f"/api/v1/workers/{worker_row.id}/plan")
    data = r.json()["data"]
    assert data["symbols"] == [
        {"symbol": "BTCUSDT", "state": "fixed"},
        {"symbol": "ETHUSDT", "state": "pending"},
    ]


def test_plan_v1_legacy_worker_compat(db, worker_row):
    """spec §4.8-3：v1 单份旧结构读 detail：symbols 长度=1、缺省返回旧那份"""
    legacy = {
        "state": "fixed",
        "ref_price": 100.0,
        "plan": _plan(100.0),
        "fixed_at": "2026-11-26T00:00:00.000000000+00:00",
    }
    worker_crud.update_worker_config(db, int(worker_row.id), {"price_plan": legacy})

    r = client.get(f"/api/v1/workers/{worker_row.id}/plan")
    data = r.json()["data"]
    assert data["state"] == "fixed"
    assert data["ref_price"] == 100.0
    assert len(data["symbols"]) == 1
    assert data["symbols"][0]["symbol"] == "BTCUSDT"  # v1 首标的推导补齐


def test_fixed_plan_reread_from_db(db, worker_row):
    """spec §5.4：固化计划以 DB 为事实源，重启路径（重新全量读库）后仍可复读"""
    worker_crud.save_worker_price_plans(
        str(worker_row.id),
        {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "state": "fixed",
                "ref_price": 100.0,
                "plan": _plan(100.0),
                "fixed_at": "2026-11-27T00:00:00.000000000+00:00",
            }
        },
    )
    first, _ = worker_crud.get_worker_price_plan(str(worker_row.id))
    again, _ = worker_crud.get_worker_price_plan(str(worker_row.id))
    assert again == first
    assert again["ref_price"] == 100.0 and again["plan"]["levels"][0]["price"] == 100.0


def test_start_accepts_ref_prices_with_null_values(monkeypatch, worker_row):
    """多标的启动：ref_prices 允许 null（缺价标的固化落 pending），不得因校验 422 阻断整个启动。"""
    called: dict = {}

    async def fake_start(worker_id, ref_price=None):
        called["ref_price"] = ref_price
        return {"status": "starting"}

    monkeypatch.setattr("worker.routes.worker_core_service.async_start_worker", fake_start)
    r = client.post(
        f"/api/v1/workers/{worker_row.id}/lifecycle/start",
        json={"ref_prices": {"BTCUSDT": 100.0, "ETHUSDT": None}},
    )
    assert r.status_code == 200, r.text
    assert called["ref_price"] == {"BTCUSDT": 100.0, "ETHUSDT": None}
