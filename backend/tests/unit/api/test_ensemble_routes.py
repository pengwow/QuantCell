from fastapi.testclient import TestClient
from fastapi import FastAPI


def test_ensemble_list_endpoint():
    from api.v2.ensemble_routes import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/v2/ensemble/list")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_ensemble_create_endpoint():
    from api.v2.ensemble_routes import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/api/v2/ensemble/create", json={
        "strategy": "soft_vote",
        "model_paths": [],
    })
    assert response.status_code == 200
    data = response.json()
    assert "ensemble_id" in data


def test_ensemble_predict_not_found():
    from api.v2.ensemble_routes import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/api/v2/ensemble/nonexistent/predict", json={
        "observation": {"market_features": [1.0, 2.0]},
    })
    assert response.status_code == 404
