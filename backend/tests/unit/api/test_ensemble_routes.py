import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# DEBUG 直通(鉴权)+ 服务隔离:ENSEMBLES_STORE 指向 tmp、清空 lru_cache 单例,
# 防止测试写入真实 backend/data/ensembles.json 或跨用例串数据。
@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEBUG", "true")
    from services import ensemble_service as es

    monkeypatch.setattr(es, "ENSEMBLES_STORE", tmp_path / "ensembles.json")
    es.get_ensemble_service.cache_clear()
    yield
    es.get_ensemble_service.cache_clear()


def _make_app():
    from api.ensemble_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_fake_members(monkeypatch, tmp_path, stems: list[str]) -> None:
    """造伪 SB3 成员:zip 空文件 + meta 旁车 + 假 load_model,免真实 SB3 训练。

    meta 旁车命名与 rl_meta_path 口径一致:{zip完整路径}.meta.json。
    """
    from gymnasium import spaces

    from services import ensemble_service as es
    from services.rl_service import RLService

    mdir = tmp_path / "models"
    mdir.mkdir()
    monkeypatch.setattr(es, "MODELS_DIR", mdir)

    class _Fake:
        action_space = spaces.Discrete(3)

        def predict(self, obs, deterministic=True):
            return 1, None

    monkeypatch.setattr(RLService, "load_model", lambda self, path: _Fake(), raising=False)

    # features 对齐真实落盘形态(rl_service.KERNEL_FEATURES):特征定义 dict 列表
    meta = {
        "spec_version": "v1",
        "window_size": 3,
        "features": [{"name": "f1", "source": {"PriceField": "f1"}, "normalizer": "ZScore", "clip_range": None}],
        "observation_stats": {},
    }
    for stem in stems:
        (mdir / f"{stem}.zip").write_bytes(b"x")
        (mdir / f"{stem}.zip.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_ensemble_list_endpoint():
    client = _make_app()
    resp = client.get("/api/v1/ensemble/list")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)


def test_ensemble_create_endpoint_rejects_non_sb3_member():
    """pickle 绝对路径成员无 meta,新校验下整单拒绝(spec §4.2)。"""
    client = _make_app()
    resp = client.post(
        "/api/v1/ensemble/create",
        json={"strategy": "soft_vote", "model_paths": ["/tmp/m1"]},
    )
    assert resp.status_code == 400
    assert "SB3" in resp.json()["detail"]


def test_ensemble_create_endpoint_with_sb3_members(monkeypatch, tmp_path):
    """SB3 stem 成员:校验通过 → records 带 members 元数据。"""
    _seed_fake_members(monkeypatch, tmp_path, ["ok1", "ok2"])

    client = _make_app()
    resp = client.post("/api/v1/ensemble/create", json={"strategy": "hard_vote", "model_paths": ["ok1", "ok2"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["skipped"] == []

    listed = client.get("/api/v1/ensemble/list").json()["data"]
    rec = next(r for r in listed if r["id"] == data["data"]["ensemble_id"])
    assert {m["stem"] for m in rec["members"]} == {"ok1", "ok2"}
    assert all(m["action_space"] == "discrete" for m in rec["members"])


def test_ensemble_delete_endpoint(monkeypatch, tmp_path):
    # 新语义下 create 拒绝 0 成员,先造一个伪成员再走创建→删除
    _seed_fake_members(monkeypatch, tmp_path, ["del_m"])
    client = _make_app()
    resp = client.post("/api/v1/ensemble/create", json={"strategy": "soft_vote", "model_paths": ["del_m"]})
    eid = resp.json()["data"]["ensemble_id"]

    resp = client.delete(f"/api/v1/ensemble/{eid}")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0

    # 删除后再删 → 404
    resp = client.delete(f"/api/v1/ensemble/{eid}")
    assert resp.status_code == 404


def test_ensemble_delete_not_found():
    client = _make_app()
    resp = client.delete("/api/v1/ensemble/nonexistent")
    assert resp.status_code == 404


def test_ensemble_predict_not_found():
    client = _make_app()
    resp = client.post("/api/v1/ensemble/nonexistent/predict", json={"observation": {}})
    assert resp.status_code == 404


def test_ensemble_predict_missing_features_returns_400(monkeypatch, tmp_path):
    """非空观测缺特征 → 服务层 ValueError → 路由 400(改动前路由未捕获会 500)。"""
    _seed_fake_members(monkeypatch, tmp_path, ["pm1"])
    client = _make_app()
    eid = client.post("/api/v1/ensemble/create", json={"model_paths": ["pm1"]}).json()["data"]["ensemble_id"]

    resp = client.post(f"/api/v1/ensemble/{eid}/predict", json={"observation": {"nope": 1.0}})
    assert resp.status_code == 400
    assert "缺少特征" in resp.json()["detail"]


def test_ensemble_backtest_endpoint(monkeypatch):
    """回测端点把参数原样透传给 RLService.run_backtest,响应兜一层 ApiResponse。"""
    captured: dict = {}

    def fake_run_backtest(self, **kwargs):
        captured.update(kwargs)
        return {"total_pnl": 1234.5, "sharpe_ratio": 1.2, "engine": "kernel"}

    from services.rl_service import RLService

    monkeypatch.setattr(RLService, "run_backtest", fake_run_backtest)

    client = _make_app()
    resp = client.post(
        "/api/v1/ensemble/abc123/backtest",
        json={"symbol": "BTCUSDT", "interval": "4h", "initial_capital": 50000.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["total_pnl"] == 1234.5
    assert captured["ensemble_id"] == "abc123"
    assert captured["engine"] == "kernel"
    assert captured["symbol"] == "BTCUSDT"
    assert captured["interval"] == "4h"
    assert captured["initial_capital"] == 50000.0


def test_ensemble_backtest_not_found_400(monkeypatch):
    """集成不存在 → 服务层 ValueError → 路由 400。"""
    from services.rl_service import RLService

    def fake_run_backtest(self, **kwargs):
        raise ValueError("集成 nope 不存在")

    monkeypatch.setattr(RLService, "run_backtest", fake_run_backtest)

    client = _make_app()
    resp = client.post("/api/v1/ensemble/nope/backtest", json={"symbol": "BTCUSDT"})
    assert resp.status_code == 400
    assert "不存在" in resp.json()["detail"]
