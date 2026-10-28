"""人工风控管控三端点 API 测试：GET/PUT/DELETE /workers/{id}/risk-control。

覆盖：无行返回 null、显式 None 落库（防 ORM 默认值坑）、422 边界校验、
未知 worker 404、幂等删除、applied 降级（driver 未运行 → on_start）。

隔离方式：core_service 直开 utils.db_session.get_db_session，底层每次调用时
从 collector.db.database 取 SessionLocal——测试内 monkeypatch 该属性指向
conftest 内存库，让 service 与用例断言共用同一 sqlite 内存库。
"""

import pytest
from sqlalchemy.orm import sessionmaker

from worker import models

# 请求统一携带 Bearer 头：conftest 的 client fixture 已 patch utils.auth.decode_jwt_token
_AUTH = {"Authorization": "Bearer test_token"}


@pytest.fixture(autouse=True)
def _no_token_refresh(monkeypatch):
    """桩掉 token 刷新判定：假 token 会触发真实解码路径，集成测试同款惯例。"""
    monkeypatch.setattr("utils.auth.should_refresh_token", lambda token: False)


@pytest.fixture
def session_factory(db_session, monkeypatch):
    """把 get_db_session 底层 SessionLocal 指到测试内存库，返回同源 sessionmaker 供造数/断言。

    内存库是 session 级 fixture（db_engine），行会跨用例残留——各用例用唯一 worker 名避开冲突。
    """
    import collector.db.database as db_mod

    sm = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    monkeypatch.setattr(db_mod, "SessionLocal", sm)
    return sm


def _create_worker(session_factory, name: str) -> models.Worker:
    """造最小 Worker 行（strategy_id=None → 推送链天然走 on_start 路径）"""
    with session_factory() as s:
        worker = models.Worker(name=name, status="stopped", strategy_id=None)
        s.add(worker)
        s.commit()
        s.refresh(worker)
        return worker


def _payload(**overrides) -> dict:
    payload = {"enabled": True}
    payload.update(overrides)
    return payload


class TestRiskControlAPI:
    def test_get_returns_null_without_row(self, client, session_factory):
        """未配置管控的 worker → GET 200 且 data 为 null（前端回落继承策略参数展示）"""
        worker = _create_worker(session_factory, "risk-api-get-null")

        resp = client.get(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH)

        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"] is None

    def test_upsert_persists_explicit_nulls(self, client, session_factory):
        """PUT 只带 enabled → DB 行 7 个数值列全部显式 None（防历史 ORM 默认值错误落库）"""
        worker = _create_worker(session_factory, "risk-api-upsert-nulls")

        resp = client.put(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH, json=_payload())

        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        with session_factory() as s:
            row = s.query(models.WorkerRiskControl).filter_by(worker_id=worker.id).one()
        assert row.enabled is True
        assert row.max_position_pct is None
        assert row.max_position_size is None
        assert row.daily_loss_amount is None
        assert row.daily_loss_limit is None
        assert row.max_drawdown is None
        assert row.max_leverage is None
        assert row.circuit_breaker_cooldown_secs is None
        assert row.updated_at is not None

    def test_upsert_validates_ranges(self, client, session_factory):
        """数值边界由 Pydantic 校验：max_leverage=999 → 422；max_position_pct=0 → 422"""
        worker = _create_worker(session_factory, "risk-api-validate")

        resp = client.put(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH, json=_payload(max_leverage=999))
        assert resp.status_code == 422

        resp = client.put(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH, json=_payload(max_position_pct=0))
        assert resp.status_code == 422

    def test_get_404_unknown_worker(self, client, session_factory):
        """未知 worker：GET/PUT/DELETE 均 404"""
        assert client.get("/api/v1/workers/9999991/risk-control", headers=_AUTH).status_code == 404
        assert client.put("/api/v1/workers/9999992/risk-control", headers=_AUTH, json=_payload()).status_code == 404
        assert client.delete("/api/v1/workers/9999993/risk-control", headers=_AUTH).status_code == 404

    def test_delete_idempotent(self, client, session_factory):
        """DELETE 两次均 200，第二次幂等；行删除后回落无管控态"""
        worker = _create_worker(session_factory, "risk-api-delete")
        assert (
            client.put(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH, json=_payload()).status_code == 200
        )

        first = client.delete(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH)
        assert first.status_code == 200
        assert first.json()["data"]["enabled"] is False
        assert first.json()["data"]["applied"] == "on_start"

        second = client.delete(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH)
        assert second.status_code == 200

        with session_factory() as s:
            assert s.query(models.WorkerRiskControl).filter_by(worker_id=worker.id).count() == 0

    def test_upsert_returns_applied(self, client, session_factory):
        """driver 未运行（get_running_driver → None）→ applied == "on_start"，无需 mock"""
        worker = _create_worker(session_factory, "risk-api-applied")

        resp = client.put(f"/api/v1/workers/{worker.id}/risk-control", headers=_AUTH, json=_payload(max_leverage=5))

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["applied"] == "on_start"
        assert data["enabled"] is True
