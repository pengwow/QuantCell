"""GET /api/v1/workers/{id}/strategy/positions 的 paper 推导兜底契约测试。

worker_positions 表只有 live 事件链路写入；paper 持仓在引擎内存不落表，
路由必须在表为空且查询 OPEN 时回退 derive_positions_from_trades（与
「交易」tab「持仓中」行同口径），否则 paper 账总览「当前持仓」恒空。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.auth import get_current_user
from worker.dependencies import get_db_session
from worker.routes import crud, router

DERIVED_ROW = {
    "id": None,
    "worker_id": 1,
    "position_id": "derived:1:BTCUSDT",
    "symbol": "BTCUSDT",
    # 对齐 derive_positions_from_trades 真实契约：canonical 键 + deprecated 别名双送
    "position_side": "long",
    "side": "long",
    "quantity": 0.5,
    "entry_price": 50000.0,
    "current_price": 51000.0,
    "unrealized_pnl": 500.0,
    "unrealized_pnl_pct": 2.0,
    "realized_pnl": 0.0,
    "margin_used": 0.0,
    "status": "OPEN",
    "opened_at": "2026-11-16T10:00:00",
    "updated_at": "2026-11-16T10:05:00",
}


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test"}
    # 默认：DB 表为空、推导返回一行 paper 持仓（各用例按需覆盖）
    monkeypatch.setattr(crud, "get_worker_positions_filtered", lambda *a, **k: [])
    monkeypatch.setattr(crud, "derive_positions_from_trades", lambda db, wid: [dict(DERIVED_ROW)])

    class _PaperWorker:
        """get_positions 表空时会查 worker 判定 trading_mode；db=None 下必须打桩"""

        def get_trading_config_dict(self):
            return {"trading_mode": "paper"}

    monkeypatch.setattr(crud, "get_worker", lambda db, wid: _PaperWorker())
    return TestClient(app)


def test_paper_fallback_returns_derived_when_table_empty(client):
    r = client.get("/api/v1/workers/1/strategy/positions").json()
    assert r["code"] == 0
    assert r["data"] == [DERIVED_ROW]


def test_db_rows_take_precedence_over_derivation(client, monkeypatch):
    db_row = {"position_id": "live-1", "status": "OPEN", "side": "long"}
    monkeypatch.setattr(crud, "get_worker_positions_filtered", lambda *a, **k: [db_row])
    monkeypatch.setattr(
        crud,
        "derive_positions_from_trades",
        lambda db, wid: (_ for _ in ()).throw(AssertionError("DB 有行不得走推导")),
    )
    r = client.get("/api/v1/workers/1/strategy/positions").json()
    assert r["data"] == [db_row]


def test_closed_query_does_not_derive(client, monkeypatch):
    monkeypatch.setattr(
        crud,
        "derive_positions_from_trades",
        lambda db, wid: (_ for _ in ()).throw(AssertionError("CLOSED 查询不走 OPEN 推导")),
    )
    r = client.get("/api/v1/workers/1/strategy/positions?status=CLOSED").json()
    assert r["code"] == 0 and r["data"] == []


def test_symbol_side_filters_apply_to_derived(client):
    r = client.get("/api/v1/workers/1/strategy/positions?symbol=ETHUSDT").json()
    assert r["data"] == []
    r = client.get("/api/v1/workers/1/strategy/positions?side=LONG").json()
    assert r["data"] == [DERIVED_ROW]  # 大写入参按小写比对命中
    r = client.get("/api/v1/workers/1/strategy/positions?side=SHORT").json()
    assert r["data"] == []
