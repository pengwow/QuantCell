# 代码因子与 LLM 挖掘路由测试（鉴权/客户端模式复刻 test_async_job_routes.py）
#
# 说明：
# - /code/validate 走沙箱合成数据（真实子进程，约 1 秒，不依赖本地 parquet）；
# - /mine/llm 用 monkeypatch 替换 job_manager.submit 与 _resolve_llm_config，
#   不打真实 LLM、不跑真实线程池，因此本文件不做模块级 skip。

import pytest
from fastapi.testclient import TestClient

from main import app
from utils.auth import get_current_user


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: {"username": "t", "id": 1}
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def isolated_catalog_db(monkeypatch):
    """代码因子档案钩子 DB 隔离：内存 SQLite，不碰开发库。

    建表口径照抄 tests/unit/factor/conftest.py 的 db_session（仅 FactorCatalog/FactorSnapshot）；
    TestClient 在独立 portal 线程执行路由，内存库需 StaticPool 单连接 + check_same_thread=False
    才能跨线程共享同一连接。monkeypatch factor.routes.get_db_session 后，路由内所有
    `with get_db_session()` 都落到本内存库；函数级 fixture 每用例一个新库，结束即销毁，无残留。
    """
    from contextlib import contextmanager

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from collector.db.database import Base
    from factor import routes as factor_routes
    from factor.models import FactorCatalog, FactorMiningRun, FactorSnapshot

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        eng,
        tables=[FactorCatalog.__table__, FactorSnapshot.__table__, FactorMiningRun.__table__],
    )
    session_factory = sessionmaker(bind=eng)

    @contextmanager
    def fake_get_db_session():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(factor_routes, "get_db_session", fake_get_db_session)
    return eng


def test_validate_code_ok(client):
    resp = client.post(
        "/api/v1/factor/code/validate",
        json={"code": 'factor = df["close"].pct_change(5)'},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["valid"] is True


def test_validate_code_rejects_import(client):
    resp = client.post("/api/v1/factor/code/validate", json={"code": "import os"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is False
    assert data["error_type"]


def test_add_and_delete_code_factor(client, tmp_path, monkeypatch, isolated_catalog_db):
    # 用临时 code store 隔离全局文件：monkeypatch factor_service._code_store
    # isolated_catalog_db：档案钩子落到内存 SQLite，不写开发库
    from factor.code_store import CodeFactorStore
    from factor.routes import factor_service

    monkeypatch.setattr(factor_service, "_code_store", CodeFactorStore(tmp_path / "c.json"))
    resp = client.post(
        "/api/v1/factor/code/add",
        json={
            "factor_name": "llm_demo_1",
            "code": 'factor = df["close"].rolling(10).mean() / df["close"] - 1',
            "description": "demo",
        },
    )
    assert resp.status_code == 200, resp.text
    assert client.delete("/api/v1/factor/code/llm_demo_1").status_code == 200


def test_add_code_factor_indexes_catalog_and_delete_cleans(client, tmp_path, monkeypatch, isolated_catalog_db):
    """POST /code/add 显式建档；DELETE /code 级联清理档案行与快照行。"""
    from sqlalchemy.orm import Session

    from factor import routes as factor_routes
    from factor.code_store import CodeFactorStore
    from factor.models import FactorCatalog, FactorSnapshot

    monkeypatch.setattr(factor_routes.factor_service, "_code_store", CodeFactorStore(tmp_path / "c.json"))

    name = "zz_code_catalog_demo"
    resp = client.post(
        "/api/v1/factor/code/add",
        json={
            "factor_name": name,
            "code": 'factor = df["close"].rolling(10).mean() / df["close"] - 1',
            "description": "demo",
        },
    )
    assert resp.status_code == 200, resp.text

    # 与生产相同的查询路径：GET /factor/catalog（内部同样 sync_builtins + 查 FactorCatalog）
    cat = client.get("/api/v1/factor/catalog")
    assert cat.status_code == 200, cat.text
    rows = [x for x in cat.json()["data"]["factors"] if x["name"] == name]
    assert len(rows) == 1
    assert rows[0]["category"] == "llm_code"
    assert rows[0]["builtin"] is False
    # 内存库直接复核列值（is_builtin=false / category=llm_code）
    with Session(isolated_catalog_db) as db:
        row = db.query(FactorCatalog).filter_by(name=name).one()
        assert row.is_builtin is False
        assert row.category == "llm_code"
        # 手工插一条快照行，验证 DELETE 钩子对 FactorSnapshot 的级联清理
        db.add(FactorSnapshot(factor_name=name, params_json="{}", metrics_json="{}", bar_count=0))
        db.commit()

    assert client.delete(f"/api/v1/factor/code/{name}").status_code == 200

    # 档案行与快照行均消失；内存库内该 name 零残留
    with Session(isolated_catalog_db) as db:
        assert db.query(FactorCatalog).filter_by(name=name).count() == 0
        assert db.query(FactorSnapshot).filter_by(factor_name=name).count() == 0


def test_add_code_factor_catalog_hook_failure_non_blocking(client, tmp_path, monkeypatch, isolated_catalog_db):
    """建档钩子抛异常时 /code/add 仍 200（代码保存不被派生档案拖垮）。"""
    from factor import routes as factor_routes
    from factor.code_store import CodeFactorStore

    monkeypatch.setattr(factor_routes.factor_service, "_code_store", CodeFactorStore(tmp_path / "c.json"))

    def _boom(db, detail):
        raise RuntimeError("catalog down")

    monkeypatch.setattr(factor_routes._catalog_service, "upsert_custom", _boom)

    name = "zz_code_hook_fail"
    resp = client.post(
        "/api/v1/factor/code/add",
        json={"factor_name": name, "code": 'factor = df["close"].pct_change(5)', "description": ""},
    )
    assert resp.status_code == 200, resp.text

    # 代码确实已保存（DELETE 成功即证明）；删除钩子在内存库上执行，不碰开发库
    assert client.delete(f"/api/v1/factor/code/{name}").status_code == 200


def test_add_code_factor_rejects_bad_code(client):
    resp = client.post(
        "/api/v1/factor/code/add",
        json={"factor_name": "x", "code": "import os"},
    )
    assert resp.status_code == 400


_COMPOSITE_BODY = {
    "factor_name": "zz_comp_demo",
    "description": "合成演示",
    "constituents": [
        {
            "code": 'factor = df["close"].pct_change(5)',
            "weight": 0.6,
            "ts_stats": {"BTCUSDT": {"mean": 0.0, "std": 1.0}},
        },
        {
            "code": 'factor = df["volume"].pct_change(5)',
            "weight": -0.4,
            "ts_stats": {"BTCUSDT": {"mean": 0.0, "std": 1.0}},
        },
    ],
    "train_window": {
        "start": "2026-01-01T00:00:00",
        "end": "2026-01-07T23:00:00",
        "interval": "1h",
        "candle_type": "spot",
    },
}


def test_add_and_delete_composite_factor(client, tmp_path, monkeypatch, isolated_catalog_db):
    from factor.composite_store import CompositeFactorStore
    from factor.routes import factor_service

    monkeypatch.setattr(factor_service, "_composite_store", CompositeFactorStore(tmp_path / "comp.json"))
    resp = client.post("/api/v1/factor/composite/add", json=_COMPOSITE_BODY)
    assert resp.status_code == 200, resp.text
    assert client.delete("/api/v1/factor/composite/zz_comp_demo").status_code == 200
    # 删除后再删 → 404
    assert client.delete("/api/v1/factor/composite/zz_comp_demo").status_code == 404


def test_add_composite_indexes_catalog_and_delete_cleans(client, tmp_path, monkeypatch, isolated_catalog_db):
    from sqlalchemy.orm import Session

    from factor import routes as factor_routes
    from factor.composite_store import CompositeFactorStore
    from factor.models import FactorCatalog, FactorSnapshot

    monkeypatch.setattr(factor_routes.factor_service, "_composite_store", CompositeFactorStore(tmp_path / "comp.json"))
    name = _COMPOSITE_BODY["factor_name"]
    resp = client.post("/api/v1/factor/composite/add", json=_COMPOSITE_BODY)
    assert resp.status_code == 200, resp.text

    cat = client.get("/api/v1/factor/catalog")
    rows = [x for x in cat.json()["data"]["factors"] if x["name"] == name]
    assert len(rows) == 1
    assert rows[0]["category"] == "llm_composite"
    assert rows[0]["builtin"] is False

    with Session(isolated_catalog_db) as db:
        row = db.query(FactorCatalog).filter_by(name=name).one()
        assert row.category == "llm_composite"
        db.add(FactorSnapshot(factor_name=name, params_json="{}", metrics_json="{}", bar_count=0))
        db.commit()

    assert client.delete(f"/api/v1/factor/composite/{name}").status_code == 200
    with Session(isolated_catalog_db) as db:
        assert db.query(FactorCatalog).filter_by(name=name).count() == 0
        assert db.query(FactorSnapshot).filter_by(factor_name=name).count() == 0


def test_add_composite_rejects_malicious_constituent(client, tmp_path, monkeypatch):
    from factor.composite_store import CompositeFactorStore
    from factor.routes import factor_service

    monkeypatch.setattr(factor_service, "_composite_store", CompositeFactorStore(tmp_path / "comp.json"))
    body = {
        **_COMPOSITE_BODY,
        "factor_name": "zz_comp_evil",
        "constituents": [
            {"code": "import os", "weight": 0.5, "ts_stats": {}},
            _COMPOSITE_BODY["constituents"][1],
        ],
    }
    resp = client.post("/api/v1/factor/composite/add", json=body)
    assert resp.status_code == 400
    assert not factor_service._composite_store.exists("zz_comp_evil")


def test_add_composite_rejects_single_constituent(client, tmp_path, monkeypatch):
    from factor.composite_store import CompositeFactorStore
    from factor.routes import factor_service

    monkeypatch.setattr(factor_service, "_composite_store", CompositeFactorStore(tmp_path / "comp.json"))
    body = {**_COMPOSITE_BODY, "constituents": [_COMPOSITE_BODY["constituents"][0]]}
    resp = client.post("/api/v1/factor/composite/add", json=body)
    assert resp.status_code == 422  # Pydantic 成分数 2-20 校验


def test_mine_llm_submits_job_and_creates_run(client, monkeypatch, isolated_catalog_db):
    submitted = {}
    captured = {}

    def fake_submit(kind, params, runner, on_terminal=None, on_event_cb=None):
        submitted["kind"] = kind
        submitted["params"] = params
        captured["on_terminal"] = on_terminal
        captured["on_event_cb"] = on_event_cb
        return "job-123"

    monkeypatch.setattr("factor.routes.job_manager.submit", fake_submit)
    monkeypatch.setattr(
        "factor.routes._resolve_llm_config",
        lambda model_id=None: {"api_key": "k", "base_url": "http://x", "model": "m"},
    )
    resp = client.post(
        "/api/v1/factor/mine/llm",
        json={
            "instruments": ["BTCUSDT", "ETHUSDT"],
            "interval": "1h",
            "candle_type": "spot",
            "start_time": None,
            "end_time": None,
            "n_candidates": 3,
            "n_rounds": 2,
            "top_k": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["job_id"] == "job-123"
    assert isinstance(data["run_id"], int)
    assert submitted["kind"] == "llm_mine"
    # compose 默认开启并透传到 job 参数
    assert submitted["params"]["compose"] is True
    # 终态回调已挂上
    assert callable(captured["on_terminal"])
    # 事件回调已挂上
    assert callable(captured["on_event_cb"])


def test_mine_llm_without_model_config_400(client, monkeypatch):
    monkeypatch.setattr("factor.routes._resolve_llm_config", lambda model_id=None: None)
    resp = client.post(
        "/api/v1/factor/mine/llm",
        json={"instruments": ["BTCUSDT"], "interval": "1h"},
    )
    assert resp.status_code == 400


_MINE_RESULT = {
    "candidates": [],
    "best": [],
    "composite": None,
    "stats": {
        "generated": 2,
        "unique": 2,
        "succeeded": 2,
        "failed": 0,
        "redundant": 0,
        "rounds": 1,
        "symbols": ["BTCUSDT"],
        "interval": "1h",
        "model_name": "m",
    },
}


def _submit_mining_with_captured_cb(client, monkeypatch, job_id="job-h1"):
    from factor.job_manager import JobStatus

    captured = {}

    def fake_submit(kind, params, runner, on_terminal=None, on_event_cb=None):
        captured["cb"] = on_terminal
        return job_id

    class _RunningJob:
        # 模拟真实 submit 的内存副作用：内存中存在 running job，
        # service 懒修正据此保持 DB running 行（查无内存 job 才会置 interrupted）
        status = JobStatus.RUNNING

    class _RunningManager:
        def get(self, jid):
            return _RunningJob() if jid == job_id else None

    monkeypatch.setattr("factor.routes.job_manager.submit", fake_submit)
    monkeypatch.setattr("factor.mining_run_service.job_manager", _RunningManager())
    monkeypatch.setattr(
        "factor.routes._resolve_llm_config",
        lambda model_id=None: {"api_key": "k", "base_url": "http://x", "model": "m"},
    )
    resp = client.post(
        "/api/v1/factor/mine/llm",
        json={"instruments": ["BTCUSDT"], "interval": "1h", "n_candidates": 2, "n_rounds": 1},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["run_id"], captured


def test_mine_run_lifecycle_list_detail_delete(client, monkeypatch, isolated_catalog_db):
    run_id, captured = _submit_mining_with_captured_cb(client, monkeypatch)

    # 初始 running：列表可见、详情可查、删除 409
    lst = client.get("/api/v1/factor/mine/runs")
    assert lst.status_code == 200, lst.text
    body = lst.json()["data"]
    assert body["total"] == 1
    assert body["runs"][0]["status"] == "running"
    assert "result" not in body["runs"][0]
    assert body["runs"][0]["params"]["instruments"] == ["BTCUSDT"]
    assert client.delete(f"/api/v1/factor/mine/runs/{run_id}").status_code == 409

    # 驱动完成回调
    captured["cb"]("job-h1", True, _MINE_RESULT)

    detail = client.get(f"/api/v1/factor/mine/runs/{run_id}").json()["data"]
    assert detail["status"] == "completed"
    assert detail["result"]["stats"]["succeeded"] == 2
    assert detail["stats"]["generated"] == 2
    assert detail["finished_at"] is not None

    assert client.delete(f"/api/v1/factor/mine/runs/{run_id}").status_code == 200
    assert client.get(f"/api/v1/factor/mine/runs/{run_id}").status_code == 404


def test_mine_run_failed_terminal_persists_error(client, monkeypatch, isolated_catalog_db):
    run_id, captured = _submit_mining_with_captured_cb(client, monkeypatch, job_id="job-h2")
    captured["cb"]("job-h2", False, "llm boom")
    detail = client.get(f"/api/v1/factor/mine/runs/{run_id}").json()["data"]
    assert detail["status"] == "failed" and detail["error"] == "llm boom"
    assert client.delete(f"/api/v1/factor/mine/runs/{run_id}").status_code == 200


def test_mine_run_interrupted_after_restart(client, monkeypatch, isolated_catalog_db):
    # DB running 但内存 job 查不到 → 详情懒修正 interrupted（monkeypatch 内存 manager.get 为 None）
    run_id, _ = _submit_mining_with_captured_cb(client, monkeypatch, job_id="job-h3")

    class _NoJobs:
        def get(self, job_id):
            return None

    monkeypatch.setattr("factor.mining_run_service.job_manager", _NoJobs())
    detail = client.get(f"/api/v1/factor/mine/runs/{run_id}").json()["data"]
    assert detail["status"] == "interrupted"


def test_get_job_events_incremental(client, monkeypatch):
    from factor.job_manager import FactorJobManager

    mgr = FactorJobManager(sweep_interval=9999)
    monkeypatch.setattr("factor.routes.job_manager", mgr)
    jid = mgr.submit("llm_mine", {}, lambda p, s, e=None: 1)
    import time as _t

    deadline = _t.time() + 3
    while mgr.get(jid).status.value != "completed" and _t.time() < deadline:
        _t.sleep(0.02)
    mgr.append_event(jid, "info", "generating", 5.0, "a")
    mgr.append_event(jid, "info", "evaluating", 9.0, "b")

    r0 = client.get(f"/api/v1/factor/jobs/{jid}/events")
    assert r0.status_code == 200, r0.text
    body = r0.json()["data"]
    assert [e["msg"] for e in body["events"]] == ["a", "b"]
    assert body["next_idx"] == 2
    r1 = client.get(f"/api/v1/factor/jobs/{jid}/events?after_idx=1")
    assert [e["msg"] for e in r1.json()["data"]["events"]] == ["b"]
    mgr.shutdown()


def test_get_job_events_404(client, monkeypatch):
    from factor.job_manager import FactorJobManager

    mgr = FactorJobManager(sweep_interval=9999)
    monkeypatch.setattr("factor.routes.job_manager", mgr)
    assert client.get("/api/v1/factor/jobs/missing/events").status_code == 404
    mgr.shutdown()


def test_events_flush_persists_to_run_detail(client, monkeypatch, isolated_catalog_db):
    # 走 fake_submit 建 running 行；直接用路由层 sink 刷事件，再查详情
    from factor.routes import _persist_events

    _submit_mining_with_captured_cb(client, monkeypatch, job_id="job-ev1")
    _persist_events("job-ev1", [{"idx": 0, "msg": "第一步"}, {"idx": 1, "msg": "第二步"}])
    # 找到该 run 的 id
    runs = client.get("/api/v1/factor/mine/runs").json()["data"]["runs"]
    run_id = runs[0]["id"]
    detail = client.get(f"/api/v1/factor/mine/runs/{run_id}").json()["data"]
    assert [e["msg"] for e in detail["events"]] == ["第一步", "第二步"]
