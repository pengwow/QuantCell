from fastapi.testclient import TestClient
from fastapi import FastAPI


def _make_app():
    from api.v2.risk_routes import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_risk_check_endpoint():
    client = _make_app()
    resp = client.post("/api/v2/risk/check", json={
        "order": {"symbol": "BTC-USDT", "side": "Buy", "quantity": 0.1, "price": 50000},
        "portfolio": {"cash": {"USD": 200000}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "passed" in data["data"]


def test_risk_metrics_endpoint():
    client = _make_app()
    resp = client.get("/api/v2/risk/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


def test_risk_reset_endpoint():
    client = _make_app()
    resp = client.post("/api/v2/risk/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "ok"
