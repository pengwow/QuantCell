from fastapi.testclient import TestClient
from fastapi import FastAPI


def _make_client():
    from api.v2.risk_routes import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_risk_check_endpoint():
    client = _make_client()
    response = client.post("/api/v2/risk/check", json={
        "order": {"symbol": "BTC-USDT", "side": "Buy", "quantity": 0.1, "price": 50000},
        "portfolio": {"cash": {"USD": 200000}},
    })
    assert response.status_code == 200
    data = response.json()
    assert "passed" in data


def test_risk_metrics_endpoint():
    client = _make_client()
    response = client.get("/api/v2/risk/metrics")
    assert response.status_code == 200


def test_risk_reset_endpoint():
    client = _make_client()
    response = client.post("/api/v2/risk/reset")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
