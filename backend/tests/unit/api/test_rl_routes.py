from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# 用 fixture + monkeypatch 设置 DEBUG，测试后自动恢复 env：
# 模块级 os.environ["DEBUG"]="true" 是进程级全局泄漏，会把后续其它测试
# （如 ai_model 认证测试，它们 patch utils.auth.IS_DEBUG_MODE=False 强制认证）
# 污染成 debug 直通，导致 401 断言失败。
@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")


def _make_app():
    from api.rl_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_train_endpoint_success():
    client = _make_app()
    mock_result = MagicMock()
    mock_result.model_id = "mock_rl_model"
    mock_result.metrics = {
        "steps": 100,
        "algorithm": "ppo",
        "elapsed_seconds": 1.0,
        "model_path": "/tmp/m.zip",
    }
    mock_result.walk_forward = None

    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.return_value = mock_result
        resp = client.post(
            "/api/v1/rl/train",
            json={"symbol": "BTCUSDT", "algorithm": "ppo", "total_timesteps": 1000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["model_id"] == "mock_rl_model"
        assert data["data"]["status"] == "completed"


def test_train_endpoint_value_error():
    """传 symbol 但后端抛 ValueError → 400"""
    client = _make_app()
    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.side_effect = ValueError("bad config")
        resp = client.post("/api/v1/rl/train", json={"symbol": "BTCUSDT"})
        assert resp.status_code == 400
        assert "bad config" in resp.json()["detail"]


def test_train_endpoint_missing_symbol_returns_422():
    """缺 symbol → Pydantic 必填校验失败 → 422"""
    client = _make_app()
    resp = client.post("/api/v1/rl/train", json={"algorithm": "ppo"})
    assert resp.status_code == 422
    body = resp.json()
    assert any("symbol" in str(err).lower() for err in body.get("detail", []))


def test_train_endpoint_defaults():
    """传 symbol 时其他字段走默认值 → 200"""
    client = _make_app()
    mock_result = MagicMock()
    mock_result.model_id = "m1"
    mock_result.metrics = {}
    mock_result.walk_forward = None

    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.return_value = mock_result
        resp = client.post("/api/v1/rl/train", json={"symbol": "BTCUSDT"})
        assert resp.status_code == 200


def test_models_endpoint():
    client = _make_app()
    with patch("services.model_registry.ModelRegistryService") as MockSvc:
        MockSvc.return_value.list_models.return_value = [{"id": "1", "name": "test"}]
        resp = client.get("/api/v1/rl/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert isinstance(data["data"], list)


def test_walk_forward_endpoint():
    client = _make_app()
    mock_result = MagicMock()
    mock_result.model_id = "wf_model"
    mock_result.walk_forward = {
        "n_splits": 3,
        "folds": [],
        "aggregate": {"mean": {}, "std": {}},
    }

    with patch("services.rl_service.RLService") as MockSvc:
        MockSvc.return_value.train.return_value = mock_result
        resp = client.post("/api/v1/rl/walk-forward", json={"symbol": "BTCUSDT", "n_splits": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "walk_forward" in data["data"]


def _mock_rl_backtest_svc():
    """构造带真实 resolve_saved_model_path 的 RLService mock（回测端点先解析路径再回测）。"""
    from pathlib import Path

    svc = MagicMock()
    real_dir = Path("/tmp/rl_test_models")
    svc.resolve_saved_model_path = lambda model_id: real_dir / f"{model_id}.zip"
    # run_backtest_task 返回任务化契约：task_id + rl_model: 前缀策略名 + 聚合指标
    svc.run_backtest_task.return_value = {
        "task_id": 1750000000000,
        "strategy_name": "rl_model:rl_model_ppo_1",
        "symbol": "BTCUSDT",
        "interval": "1h",
        "engine": "kernel",
        "total_pnl": 1.0,
        "total_return_pct": 0.001,
        "sharpe_ratio": 0.5,
        "max_drawdown_pct": 1.0,
        "win_rate": 0.6,
        "num_trades": 3,
        "data_bars": 100,
    }
    return svc


def test_backtest_endpoint_success():
    """model_id 合法且文件存在 → 落库任务行并透传 run_backtest_task 返回"""
    client = _make_app()
    svc = _mock_rl_backtest_svc()
    # 预置真实模型文件，让 is_file() 校验通过
    model_dir = svc.resolve_saved_model_path("rl_model_ppo_1").parent
    model_dir.mkdir(parents=True, exist_ok=True)
    model_zip = svc.resolve_saved_model_path("rl_model_ppo_1")
    model_zip.write_bytes(b"stub")

    # 端点的 DB 写入为函数内 import（from utils.db_session import get_db_session），
    # patch utils.db_session.get_db_session 即可拦截（MagicMock 天然支持 with 语义）。
    # 必须连 BacktestTask 一起 mock：构造 declarative 实例会触发全 registry 的
    # mapper 配置，而本测试只挂 rl_routes 子路由、没有 import 全部模型
    # （main.py 启动才全量注册），Worker 的 relationship('Strategy') 会解析失败。
    mock_session = MagicMock()
    with (
        patch("services.rl_service.RLService", return_value=svc),
        patch("utils.db_session.get_db_session", return_value=mock_session),
        patch("backtest.models.BacktestTask"),
    ):
        resp = client.post(
            "/api/v1/rl/backtest",
            json={"model_id": "rl_model_ppo_1", "symbol": "BTCUSDT"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["task_id"] == 1750000000000
        assert data["data"]["strategy_name"] == "rl_model:rl_model_ppo_1"
        assert data["data"]["engine"] == "kernel"
        svc.run_backtest_task.assert_called_once()
        call = svc.run_backtest_task.call_args
        assert call.args[0] == "rl_model_ppo_1"
        assert call.args[1] == "BTCUSDT"
        # 任务行已写库：get_db_session() 直接返回 mock_session 本体，with 进入后的
        # db 即 mock_session.__enter__ 的返回值
        mock_session.__enter__.return_value.add.assert_called_once()

    model_zip.unlink()
    model_dir.rmdir()


def test_backtest_endpoint_model_not_found():
    """model_id 文件不存在 → 404，不触达回测"""
    client = _make_app()
    svc = _mock_rl_backtest_svc()

    with patch("services.rl_service.RLService", return_value=svc):
        resp = client.post(
            "/api/v1/rl/backtest",
            json={"model_id": "no_such_model", "symbol": "BTCUSDT"},
        )
        assert resp.status_code == 404
        assert "no_such_model" in resp.json()["detail"]
        svc.run_backtest_task.assert_not_called()


def test_backtest_endpoint_ensemble_skips_model_file_check():
    """ensemble_id 非空 → 跳过单模型文件校验，直接聚合回测"""
    client = _make_app()
    svc = _mock_rl_backtest_svc()
    svc.run_backtest_task.return_value = {**svc.run_backtest_task.return_value, "strategy_name": "rl_ensemble:ens_1"}
    # 不预置任何模型文件：ensemble 分支不做 is_file 校验

    mock_session = MagicMock()
    with (
        patch("services.rl_service.RLService", return_value=svc),
        patch("utils.db_session.get_db_session", return_value=mock_session),
        patch("backtest.models.BacktestTask"),
    ):
        resp = client.post(
            "/api/v1/rl/backtest",
            json={"model_id": "ignored", "symbol": "BTCUSDT", "ensemble_id": "ens_1"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["strategy_name"] == "rl_ensemble:ens_1"
        assert svc.run_backtest_task.call_args.kwargs["ensemble_id"] == "ens_1"


def test_backtest_endpoint_path_traversal_rejected():
    """model_id 含路径分隔符 → 400，不触达回测"""
    client = _make_app()
    svc = MagicMock()
    svc.resolve_saved_model_path.side_effect = ValueError("非法的模型 ID: '../etc/passwd'")

    with patch("services.rl_service.RLService", return_value=svc):
        resp = client.post(
            "/api/v1/rl/backtest",
            json={"model_id": "../etc/passwd", "symbol": "BTCUSDT"},
        )
        assert resp.status_code == 400
        svc.run_backtest_task.assert_not_called()


def test_backtest_endpoint_missing_symbol_returns_422():
    client = _make_app()
    resp = client.post("/api/v1/rl/backtest", json={"model_id": "m1"})
    assert resp.status_code == 422
