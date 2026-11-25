"""训练产物 → 部署 spec：`POST /api/v1/rl/train/{task_id}/deploy-spec` 契约测试。

覆盖：策略行幂等 upsert（同一 strategy.id）、worker body 通过 WorkerCreate 校验、
前置校验早失败（任务未终态 409 / 任务不存在 404 / 产物缺失 404 / spec_version 422）、
同名非 RL 策略冲突 409、initial_capital 从已有参数继承。

不依赖真实训练：task 由 runner 注入假 train_fn 造出终态；模型产物是 tmp_path 下
的桩文件（zip 字节 + meta 旁车）。
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import rl_task_runner as runner
from services.rl_service import DEPLOY_STRATEGY_PREFIX, KERNEL_SPEC_VERSION


@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture(autouse=True)
def _clean_registry():
    runner.reset_tasks()
    yield
    # 等训练线程推进到终态再清任务表（避免下一个用例撞上仍在跑的旧任务）
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(s["status"] in runner.TERMINAL_STATUSES for s in runner.list_tasks()):
            break
        time.sleep(0.01)
    runner.reset_tasks()


@pytest.fixture
def cleanup_strategies():
    """收集用例产生的策略行名，结束后清掉，避免污染会话级测试库副本。"""
    names: list[str] = []
    yield names
    from strategy.models import Strategy
    from utils.db_session import get_db_session

    with get_db_session() as db:
        db.query(Strategy).filter(Strategy.name.in_(names)).delete(synchronize_session=False)
        db.commit()


def _make_client() -> TestClient:
    from api.rl_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _artifact(tmp_path, model_id: str, *, spec_version: str = KERNEL_SPEC_VERSION) -> str:
    """造训练产物：<model_id>.zip + <model_id>.zip.meta.json（训练落盘同构）。"""
    zip_path = tmp_path / f"{model_id}.zip"
    zip_path.write_bytes(b"stub-model")
    meta = {"model_id": model_id, "spec_version": spec_version, "window_size": 1, "features": []}
    (tmp_path / f"{model_id}.zip.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return str(zip_path)


def _wait(predicate, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("等待超时")


def _done_task(model_path: str) -> str:
    """造一个 done 状态的训练任务（假训练只回 model_path）。"""
    task_id = runner.submit_train_task(None, train_fn=lambda c, r: SimpleNamespace(model_id="m", model_path=model_path))
    _wait(lambda: runner.get_task(task_id).snapshot()["status"] == "done")
    return task_id


def test_deploy_spec_creates_rl_strategy_and_postable_worker_body(tmp_path, cleanup_strategies):
    from worker import schemas

    model_id = "rl_model_ppo_deploy_1"
    model_path = _artifact(tmp_path, model_id)
    task_id = _done_task(model_path)
    cleanup_strategies.append(f"{DEPLOY_STRATEGY_PREFIX}{model_id}")

    resp = _make_client().post(f"/api/v1/rl/train/{task_id}/deploy-spec")

    assert resp.status_code == 200
    body = resp.json()
    strategy = body["strategy"]
    assert strategy["name"] == f"{DEPLOY_STRATEGY_PREFIX}{model_id}"
    assert strategy["strategy_type"] == "rl"
    assert isinstance(strategy["id"], int) and strategy["id"] > 0
    # 语义核心：parameters 是 JSON object（upload 路由写的数组形态对 RL 无效）
    assert isinstance(strategy["parameters"], dict)
    assert strategy["parameters"]["model_path"] == str((tmp_path / f"{model_id}.zip").resolve())
    assert strategy["parameters"]["spec_version"] == KERNEL_SPEC_VERSION

    worker = body["worker"]
    assert worker["name"] == f"rl-{model_id}"
    assert worker["strategy_id"] == strategy["id"]
    assert worker["strategy_name"] == strategy["name"]
    assert worker["strategy_file_name"] is None
    assert worker["trading_config"] == {
        "exchange": "binance",
        "symbols_config": {"type": "symbols", "symbols": []},
        "interval": "1h",
        "market_type": "futures",
        "trading_mode": "paper",
    }
    assert worker["config"] == {"initial_capital": 100_000.0}

    # extra="forbid" 下无多余字段，可直接 POST /api/v1/workers
    parsed = schemas.WorkerCreate(**worker)
    assert parsed.strategy_id == strategy["id"]


def test_deploy_spec_carries_symbol_query(tmp_path, cleanup_strategies):
    model_id = "rl_model_ppo_deploy_symbol"
    task_id = _done_task(_artifact(tmp_path, model_id))
    cleanup_strategies.append(f"{DEPLOY_STRATEGY_PREFIX}{model_id}")

    resp = _make_client().post(f"/api/v1/rl/train/{task_id}/deploy-spec?symbol=btcusdt")

    assert resp.status_code == 200
    assert resp.json()["worker"]["trading_config"]["symbols_config"]["symbols"] == ["BTCUSDT"]


def test_deploy_spec_is_idempotent(tmp_path, cleanup_strategies):
    model_id = "rl_model_ppo_deploy_idem"
    task_id = _done_task(_artifact(tmp_path, model_id))
    name = f"{DEPLOY_STRATEGY_PREFIX}{model_id}"
    cleanup_strategies.append(name)
    client = _make_client()

    first = client.post(f"/api/v1/rl/train/{task_id}/deploy-spec").json()
    second = client.post(f"/api/v1/rl/train/{task_id}/deploy-spec").json()

    assert first["strategy"]["id"] == second["strategy"]["id"]
    assert first["worker"]["strategy_id"] == second["worker"]["strategy_id"]

    from strategy.models import Strategy
    from utils.db_session import get_db_session

    with get_db_session() as db:
        rows = db.query(Strategy).filter(Strategy.name == name).all()
    assert len(rows) == 1
    assert rows[0].strategy_type == "rl"


def test_deploy_spec_inherits_initial_capital_from_existing_row(tmp_path, cleanup_strategies):
    model_id = "rl_model_ppo_deploy_capital"
    task_id = _done_task(_artifact(tmp_path, model_id))
    name = f"{DEPLOY_STRATEGY_PREFIX}{model_id}"
    cleanup_strategies.append(name)
    client = _make_client()

    first = client.post(f"/api/v1/rl/train/{task_id}/deploy-spec").json()

    # 用户在策略库手改过 initial_capital：再次部署应继承而不是抹掉
    from strategy.models import Strategy
    from utils.db_session import get_db_session

    with get_db_session() as db:
        row = db.query(Strategy).filter(Strategy.name == name).one()
        params = json.loads(row.parameters)
        params["initial_capital"] = 50_000
        row.parameters = json.dumps(params)
        db.commit()

    second = client.post(f"/api/v1/rl/train/{task_id}/deploy-spec").json()

    assert second["strategy"]["id"] == first["strategy"]["id"]
    assert second["strategy"]["parameters"]["initial_capital"] == 50_000
    assert second["worker"]["config"]["initial_capital"] == 50_000


def test_deploy_spec_unfinished_task_returns_409():
    gate = threading.Event()
    task_id = runner.submit_train_task(
        None, train_fn=lambda c, r: (gate.wait(5), SimpleNamespace(model_id="m", model_path="/tmp/x.zip"))[1]
    )
    try:
        resp = _make_client().post(f"/api/v1/rl/train/{task_id}/deploy-spec")
        assert resp.status_code == 409
        assert "未完成" in resp.json()["detail"]
    finally:
        gate.set()


def test_deploy_spec_unknown_task_returns_404():
    resp = _make_client().post("/api/v1/rl/train/rltrain_nope/deploy-spec")
    assert resp.status_code == 404


def test_deploy_spec_missing_model_file_returns_404(tmp_path):
    task_id = _done_task(str(tmp_path / "ghost_model.zip"))
    resp = _make_client().post(f"/api/v1/rl/train/{task_id}/deploy-spec")
    assert resp.status_code == 404
    assert "模型文件不存在" in resp.json()["detail"]


def test_deploy_spec_missing_meta_returns_404(tmp_path):
    model_id = "rl_model_ppo_no_meta"
    zip_path = tmp_path / f"{model_id}.zip"
    zip_path.write_bytes(b"stub-model")  # 只有 zip，没有 .meta.json
    task_id = _done_task(str(zip_path))

    resp = _make_client().post(f"/api/v1/rl/train/{task_id}/deploy-spec")
    assert resp.status_code == 404
    assert "观测规格元数据" in resp.json()["detail"]


def test_deploy_spec_spec_version_mismatch_returns_422(tmp_path, cleanup_strategies):
    model_id = "rl_model_ppo_bad_spec"
    task_id = _done_task(_artifact(tmp_path, model_id, spec_version="v0"))
    cleanup_strategies.append(f"{DEPLOY_STRATEGY_PREFIX}{model_id}")

    resp = _make_client().post(f"/api/v1/rl/train/{task_id}/deploy-spec")

    assert resp.status_code == 422
    assert "spec_version" in resp.json()["detail"]

    # 校验早于写库：失败不留半截策略行
    from strategy.models import Strategy
    from utils.db_session import get_db_session

    with get_db_session() as db:
        assert db.query(Strategy).filter(Strategy.name == f"{DEPLOY_STRATEGY_PREFIX}{model_id}").first() is None


def test_deploy_spec_conflicts_with_non_rl_strategy_of_same_name(tmp_path, cleanup_strategies):
    from strategy.models import Strategy
    from utils.db_session import get_db_session

    model_id = "rl_model_ppo_name_clash"
    name = f"{DEPLOY_STRATEGY_PREFIX}{model_id}"
    task_id = _done_task(_artifact(tmp_path, model_id))
    cleanup_strategies.append(name)

    with get_db_session() as db:
        db.add(
            Strategy(
                name=name,
                strategy_type="rule",
                file_name=f"{name}.py",
                code="class X: pass",
                parameters=json.dumps([{"name": "fast", "type": "int", "default": 10}]),
            )
        )
        db.commit()

    resp = _make_client().post(f"/api/v1/rl/train/{task_id}/deploy-spec")

    assert resp.status_code == 409
    # 不覆盖用户源码策略
    with get_db_session() as db:
        row = db.query(Strategy).filter(Strategy.name == name).one()
        assert row.strategy_type == "rule"
