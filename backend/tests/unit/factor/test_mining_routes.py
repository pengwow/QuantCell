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
    from factor.models import FactorCatalog, FactorSnapshot

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng, tables=[FactorCatalog.__table__, FactorSnapshot.__table__])
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


def test_mine_llm_submits_job(client, monkeypatch):
    submitted = {}

    def fake_submit(kind, params, runner):
        submitted["kind"] = kind
        submitted["params"] = params
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
    assert resp.json()["data"]["job_id"] == "job-123"
    assert submitted["kind"] == "llm_mine"


def test_mine_llm_without_model_config_400(client, monkeypatch):
    monkeypatch.setattr("factor.routes._resolve_llm_config", lambda model_id=None: None)
    resp = client.post(
        "/api/v1/factor/mine/llm",
        json={"instruments": ["BTCUSDT"], "interval": "1h"},
    )
    assert resp.status_code == 400
