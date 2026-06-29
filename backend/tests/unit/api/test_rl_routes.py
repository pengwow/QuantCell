from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI


def _make_app():
    from api.v2.rl_routes import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_train_endpoint_success():
    client = _make_app()
    mock_result = MagicMock()
    mock_result.model_id = "mock_rl_model"
    mock_result.metrics = {"steps": 100, "algorithm": "ppo", "elapsed_seconds": 1.0, "model_path": "/tmp/m.zip"}
    mock_result.walk_forward = None

    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.return_value = mock_result
        resp = client.post("/api/v2/rl/train", json={"symbol": "BTCUSDT", "algorithm": "ppo", "total_timesteps": 1000})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["model_id"] == "mock_rl_model"
        assert data["data"]["status"] == "completed"


def test_train_endpoint_value_error():
    client = _make_app()
    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.side_effect = ValueError("bad config")
        resp = client.post("/api/v2/rl/train", json={"algorithm": "ppo"})
        assert resp.status_code == 400
        assert "bad config" in resp.json()["detail"]


def test_train_endpoint_defaults():
    client = _make_app()
    mock_result = MagicMock()
    mock_result.model_id = "m1"
    mock_result.metrics = {}
    mock_result.walk_forward = None

    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.return_value = mock_result
        resp = client.post("/api/v2/rl/train", json={})
        assert resp.status_code == 200


def test_models_endpoint():
    client = _make_app()
    with patch("services.model_registry.ModelRegistryService") as MockSvc:
        MockSvc.return_value.list_models.return_value = [{"id": "1", "name": "test"}]
        resp = client.get("/api/v2/rl/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert isinstance(data["data"], list)


def test_walk_forward_endpoint():
    client = _make_app()
    mock_result = MagicMock()
    mock_result.model_id = "wf_model"
    mock_result.walk_forward = {"n_splits": 3, "folds": [], "aggregate": {"mean": {}, "std": {}}}

    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.return_value = mock_result
        resp = client.post("/api/v2/rl/walk-forward", json={"symbol": "BTCUSDT", "n_splits": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "walk_forward" in data["data"]


def test_hpo_not_implemented():
    client = _make_app()
    resp = client.post("/api/v2/rl/hpo")
    assert resp.status_code == 501
