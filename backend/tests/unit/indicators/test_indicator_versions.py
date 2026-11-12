"""指标版本快照单元测试（P2-08）。

覆盖：
1. record_version 版本号单调递增（首快照=v1，save 递增）
2. list_versions 排序与 is_current 标记
3. rollback：内容写回 + 生成 source="rollback" 新快照（历史不丢）
4. diff_versions 返回两版本代码
5. /versions、/versions/diff、/rollback、/preview 路由冒烟（内存库 + TestClient）
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db.database import Base, _import_all_models
from indicators.models import CustomIndicator
from indicators.versions import IndicatorVersionBusiness

_import_all_models()


@pytest.fixture()
def version_db_engine():
    """函数级内存库：每个用例一张干净库。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def version_db(version_db_engine, monkeypatch):
    """替换全局 SessionLocal 指向内存库，engine 置哨兵让 init_database_config 短路。"""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=version_db_engine)
    from collector.db import database as db_module

    monkeypatch.setattr(db_module, "SessionLocal", factory)
    monkeypatch.setattr(db_module, "engine", object(), raising=False)
    return factory


@pytest.fixture()
def client(version_db, monkeypatch):
    """挂载指标路由的 TestClient，guest 判定固定放行（与 alert_client 同模式）。"""
    from indicators import routes as indicator_routes

    monkeypatch.setattr(indicator_routes, "is_guest_user", lambda request: False)
    app = FastAPI()
    app.include_router(indicator_routes.router)
    return TestClient(app)


def _seed_indicator(factory, code: str = "v1_code", name: str = "测试指标") -> int:
    with factory() as db:
        row = CustomIndicator(user_id=1, name=name, code=code)
        db.add(row)
        db.commit()
        return row.id


def _get_indicator(factory, indicator_id: int) -> CustomIndicator:
    with factory() as db:
        row = db.query(CustomIndicator).filter_by(id=indicator_id).first()
        assert row is not None
        db.refresh(row)
        # 脱离 session 后再读属性，避免 DetachedInstanceError
        db.expunge(row)
        return row


class TestRecordVersion:
    def test_first_and_increment(self, version_db):
        """首快照 = indicators.version(1)，之后每次 +1。"""
        indicator_id = _seed_indicator(version_db)

        v1 = IndicatorVersionBusiness.record_version(indicator_id, source="create")
        assert v1 == 1
        v2 = IndicatorVersionBusiness.record_version(indicator_id, source="save")
        assert v2 == 2

        row = _get_indicator(version_db, indicator_id)
        assert row.version == 2

    def test_missing_indicator(self, version_db):
        assert IndicatorVersionBusiness.record_version(999, source="save") is None


class TestListAndDiff:
    def test_list_versions_order_and_current(self, version_db):
        indicator_id = _seed_indicator(version_db)
        IndicatorVersionBusiness.record_version(indicator_id, source="create")
        IndicatorVersionBusiness.record_version(indicator_id, source="save")

        versions = IndicatorVersionBusiness.list_versions(indicator_id)
        assert [v["version_no"] for v in versions] == [2, 1]  # 新版本在前
        assert versions[0]["is_current"] is True
        assert versions[1]["is_current"] is False
        assert versions[1]["source"] == "create"

    def test_diff_versions(self, version_db):
        indicator_id = _seed_indicator(version_db, code="code_a")
        IndicatorVersionBusiness.record_version(indicator_id, source="create")
        with version_db() as db:
            db.query(CustomIndicator).filter_by(id=indicator_id).update({"code": "code_b"})
            db.commit()
        IndicatorVersionBusiness.record_version(indicator_id, source="save")

        diff = IndicatorVersionBusiness.diff_versions(indicator_id, 1, 2)
        assert diff["a"]["code"] == "code_a"
        assert diff["b"]["code"] == "code_b"

    def test_diff_missing(self, version_db):
        indicator_id = _seed_indicator(version_db)
        IndicatorVersionBusiness.record_version(indicator_id, source="create")
        assert IndicatorVersionBusiness.diff_versions(indicator_id, 1, 99) is None


class TestRollback:
    def test_rollback_creates_new_snapshot(self, version_db):
        """回滚 = 旧内容写回 + source="rollback" 的新快照，历史不丢。"""
        indicator_id = _seed_indicator(version_db, code="old_code", name="旧名字")
        IndicatorVersionBusiness.record_version(indicator_id, source="create")

        with version_db() as db:
            db.query(CustomIndicator).filter_by(id=indicator_id).update({"code": "new_code", "name": "新名字"})
            db.commit()
        IndicatorVersionBusiness.record_version(indicator_id, source="save")

        result = IndicatorVersionBusiness.rollback(indicator_id, 1)
        assert result is not None
        assert result["code"] == "old_code"
        assert result["name"] == "旧名字"
        assert result["version"] == 3  # 回滚产生 v3

        row = _get_indicator(version_db, indicator_id)
        assert row.code == "old_code"

        versions = IndicatorVersionBusiness.list_versions(indicator_id)
        assert [v["version_no"] for v in versions] == [3, 2, 1]
        assert versions[0]["source"] == "rollback"

    def test_rollback_missing_version(self, version_db):
        indicator_id = _seed_indicator(version_db)
        IndicatorVersionBusiness.record_version(indicator_id, source="create")
        assert IndicatorVersionBusiness.rollback(indicator_id, 99) is None


class TestRoutes:
    def test_full_flow(self, client, version_db):
        """create(自动v1) → update(自动v2) → versions → diff → rollback 端到端。"""
        resp = client.post("/api/v1/indicators", json={"name": "流指标", "code": "c = 1"})
        assert resp.status_code == 200
        indicator_id = resp.json()["data"]["id"]

        client.put(f"/api/v1/indicators/{indicator_id}", json={"code": "c = 2"})

        versions = client.get(f"/api/v1/indicators/{indicator_id}/versions").json()["data"]
        assert [v["version_no"] for v in versions] == [2, 1]
        assert {v["source"] for v in versions} == {"create", "save"}

        diff = client.get(f"/api/v1/indicators/{indicator_id}/versions/diff?a=1&b=2").json()["data"]
        assert diff["a"]["code"] == "c = 1"
        assert diff["b"]["code"] == "c = 2"

        rolled = client.post(f"/api/v1/indicators/{indicator_id}/versions/1/rollback")
        assert rolled.status_code == 200
        data = rolled.json()["data"]
        assert data["code"] == "c = 1"
        assert data["version"] == 3

    def test_rollback_404(self, client, version_db):
        resp = client.post("/api/v1/indicators/999/versions/1/rollback")
        assert resp.json()["code"] == 404

    def test_preview_endpoint(self, client, version_db):
        """/preview 不落库直接求值草稿代码。"""
        code = """
df = df.copy()
output = {
    "name": "P",
    "plots": [{"name": "close", "data": df["close"].tolist(), "color": "#ff0000", "overlay": True}],
    "signals": [],
}
"""
        resp = client.post("/api/v1/indicators/preview", json={"code": code})
        body = resp.json()
        assert body["code"] == 0
        result = body["data"]
        assert result["success"] is True
        assert len(result["plots"]) == 1
        # 草稿未保存：指标数量不变
        assert len(client.get("/api/v1/indicators").json()["data"]) == 0

    def test_preview_syntax_error(self, client, version_db):
        resp = client.post("/api/v1/indicators/preview", json={"code": "def def("})
        body = resp.json()
        assert body["code"] == 400
        assert body["data"]["success"] is False
