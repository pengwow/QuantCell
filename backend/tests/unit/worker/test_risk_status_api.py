"""GET /workers/{id}/risk-status API 测试（spec 2026-11-16 §7）。

隔离方式沿用 test_risk_control_api.py：client fixture 先拉起 app 完成 DB 初始化，
session_factory 再把 get_db_session 底层的 collector.db.database.SessionLocal 指向
测试内存库，core_service 查询与用例断言共用同一 sqlite 内存库。
"""

import pytest
from sqlalchemy.orm import sessionmaker

from strategy.models import Strategy
from worker import models

# 请求统一携带 Bearer 头：conftest 的 client fixture 已 patch utils.auth.decode_jwt_token
_AUTH = {"Authorization": "Bearer test_token"}

BASE = "/api/v1/workers"


@pytest.fixture(autouse=True)
def _no_token_refresh(monkeypatch):
    """桩掉 token 刷新判定：假 token 会触发真实解码路径，集成测试同款惯例。"""
    monkeypatch.setattr("utils.auth.should_refresh_token", lambda token: False)


@pytest.fixture
def session_factory(db_session, monkeypatch):
    """把 get_db_session 底层 SessionLocal 指到测试内存库，返回同源 sessionmaker 供造数/断言。

    内存库是 session 级 fixture（db_engine），行会跨用例残留——worker/strategy 名唯一避开冲突。
    """
    import collector.db.database as db_mod

    sm = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    monkeypatch.setattr(db_mod, "SessionLocal", sm)
    return sm


def _create_worker(session_factory, name: str, strategy_id: int | None = None) -> models.Worker:
    """造最小 Worker 行（strategy_id=None → 无策略参数，risk-status 走 none/manual 态）"""
    with session_factory() as s:
        worker = models.Worker(name=name, status="stopped", strategy_id=strategy_id)
        s.add(worker)
        s.commit()
        s.refresh(worker)
        return worker


class TestRiskStatusAPI:
    def test_risk_status_not_configured(self, client, session_factory):
        """无人工管控行且策略参数无 risk 块 → 200，三态为 none"""
        worker = _create_worker(session_factory, "risk-status-api-none")

        resp = client.get(f"{BASE}/{worker.id}/risk-status", headers=_AUTH)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert resp.json()["code"] == 0
        assert data["configured"] is False
        assert data["source"] == "none"
        assert data["config"] is None
        assert data["daily_pnl"] == 0.0  # 无成交记录，当日盈亏为 0（同源聚合通道接通）
        assert data["circuit_breaker_tripped"] is False

    def test_risk_status_manual(self, client, session_factory):
        """人工管控行 → source=manual；金额口径取 pct×cash
        （max_position_size 显式写大值压过历史 ORM default=1.0，否则 min(50000, 1.0) 会误判）"""
        worker = _create_worker(session_factory, "risk-status-api-manual")
        with session_factory() as s:
            s.add(
                models.WorkerRiskControl(
                    worker_id=worker.id,
                    enabled=True,
                    max_position_size=99999.0,
                    max_position_pct=0.5,
                    daily_loss_amount=2000.0,
                )
            )
            s.commit()

        resp = client.get(f"{BASE}/{worker.id}/risk-status", headers=_AUTH)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["configured"] is True
        assert data["source"] == "manual" and data["enabled"] is True
        assert data["config"]["max_position_value"] == 50000.0
        assert data["daily_loss_limit"] == 2000.0
        assert data["circuit_breaker_tripped"] is False  # 当日无亏损，不触发

    def test_risk_status_params_passthrough(self, client, session_factory):
        """策略参数带 risk 块（无人工行）→ source=params，risk 键原样直通"""
        with session_factory() as s:
            strategy = Strategy(
                name="risk-status-api-params-strategy",
                parameters='{"risk": {"max_daily_loss": 500.0}}',
            )
            s.add(strategy)
            s.commit()
            s.refresh(strategy)
            strategy_id = strategy.id
        worker = _create_worker(session_factory, "risk-status-api-params", strategy_id=strategy_id)

        resp = client.get(f"{BASE}/{worker.id}/risk-status", headers=_AUTH)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["configured"] is True
        assert data["source"] == "params" and data["enabled"] is True
        assert data["config"] == {"max_daily_loss": 500.0}
        assert data["daily_loss_limit"] == 500.0

    def test_risk_status_404(self, client, session_factory):
        """未知 worker → 404（挂 session_factory 保证查询也走测试内存库，不碰开发库）"""
        assert client.get(f"{BASE}/999999/risk-status", headers=_AUTH).status_code == 404
