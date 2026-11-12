"""指标信号提醒单元测试（P2-07）。

覆盖：
1. check_condition 纯条件判定（gt/lt/cross_up/cross_down 边界）
2. extract_plot_values plot 选择与数据清洗
3. run_evaluation_round 全流程：评估 → 去重窗口 → last_fired_at
4. alerts_routes CRUD 与测试发送冒烟（内存库 + TestClient）
"""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db.database import Base, _import_all_models
from indicators import alerts
from indicators.models import CustomIndicator, IndicatorAlertRule

_import_all_models()


@pytest.fixture()
def alert_db_engine():
    """函数级内存库：每个用例一张干净库，避免跨用例数据串扰。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def alert_db(alert_db_engine, monkeypatch):
    """函数级 sessionmaker 并替换 collector.db.database 的全局引用。

    engine 置为非空哨兵：让 get_db_session 内的 init_database_config 短路，
    避免测试摸真实 DB 文件。
    """
    factory = sessionmaker(autocommit=False, autoflush=False, bind=alert_db_engine)
    from collector.db import database as db_module

    monkeypatch.setattr(db_module, "SessionLocal", factory)
    monkeypatch.setattr(db_module, "engine", object(), raising=False)
    return factory


class FakeExecutor:
    """替身执行器：跳过沙箱，直接返回预设 plot 数据。"""

    def __init__(self, plots):
        self.plots = plots
        self.calls = []

    async def execute(self, code=None, kline_data=None, params=None, **kw):
        self.calls.append(code)
        return {"success": True, "name": "X", "plots": self.plots, "signals": []}


def _bars(n: int = 5) -> list[dict]:
    return [
        {
            "timestamp": (1_700_000_000 + i * 3600) * 10**9,
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1.0,
        }
        for i in range(n)
    ]


def _seed_indicator(factory, code: str = "c = close") -> int:
    with factory() as db:
        row = CustomIndicator(user_id=1, name="测试指标", code=code)
        db.add(row)
        db.commit()
        return row.id


def _seed_rule(factory, indicator_id: int, **kw) -> int:
    payload = dict(
        indicator_id=indicator_id,
        symbol="BTCUSDT",
        period="1h",
        op="gt",
        threshold=100.0,
        channels='["websocket"]',
        frequency=30,
        enabled=True,
    )
    payload.update(kw)
    with factory() as db:
        row = IndicatorAlertRule(**payload)
        db.add(row)
        db.commit()
        return row.id


class TestCheckCondition:
    def test_gt_lt(self):
        assert alerts.check_condition([50.0, 110.0], "gt", 100.0)
        assert not alerts.check_condition([50.0, 100.0], "gt", 100.0)  # 等值不算
        assert alerts.check_condition([150.0, 90.0], "lt", 100.0)
        assert not alerts.check_condition([], "gt", 0.0)  # 空序列不触发

    def test_cross_up_down(self):
        # 上穿：前一根 <= 阈值，最新一根 > 阈值
        assert alerts.check_condition([99.9, 100.1], "cross_up", 100.0)
        assert not alerts.check_condition([100.5, 101.0], "cross_up", 100.0)  # 都在上
        assert alerts.check_condition([100.1, 99.9], "cross_down", 100.0)
        assert not alerts.check_condition([50.0, 60.0], "cross_up", 100.0)  # 都在下
        assert not alerts.check_condition([101.0], "cross_up", 100.0)  # 单根不够

    def test_unknown_op(self):
        assert not alerts.check_condition([110.0], "between", 100.0)


class TestExtractPlotValues:
    def test_by_name_and_fallback(self):
        result = {"plots": [{"name": "a", "data": [1, 2]}, {"name": "b", "data": [3, 4]}]}
        assert alerts.extract_plot_values(result, "b") == [3.0, 4.0]
        assert alerts.extract_plot_values(result, "") == [1.0, 2.0]  # 空 plot 名回落第一个
        assert alerts.extract_plot_values(result, "missing") == [1.0, 2.0]
        assert alerts.extract_plot_values({"plots": []}, "") is None

    def test_data_cleaning(self):
        result = {"plots": [{"name": "a", "data": [1, None, float("nan"), float("inf"), "x", 5]}]}
        assert alerts.extract_plot_values(result, "a") == [1.0, 5.0]


class TestRunEvaluationRound:
    def test_trigger_writes_dedup_window(self, alert_db):
        ind_id = _seed_indicator(alert_db)
        rule_id = _seed_rule(alert_db, ind_id)
        executor = FakeExecutor([{"name": "ma", "data": [90.0, 110.0]}])

        triggers = alerts.run_evaluation_round(executor=executor, fetch_kline=lambda rule: _bars())
        assert len(triggers) == 1
        assert triggers[0]["rule"]["id"] == rule_id
        assert triggers[0]["evaluation"]["value"] == 110.0
        assert executor.calls == ["c = close"]  # 指标代码按 indicator_id 关联

        with alert_db() as db:
            assert db.get(IndicatorAlertRule, rule_id).last_fired_at is not None

        # 去重窗口内第二轮不触发
        assert alerts.run_evaluation_round(executor=executor, fetch_kline=lambda rule: _bars()) == []

    def test_not_triggered_keeps_window_clear(self, alert_db):
        ind_id = _seed_indicator(alert_db)
        rule_id = _seed_rule(alert_db, ind_id)
        executor = FakeExecutor([{"name": "ma", "data": [50.0, 60.0]}])  # 低于阈值

        assert alerts.run_evaluation_round(executor=executor, fetch_kline=lambda rule: _bars()) == []
        with alert_db() as db:
            assert db.get(IndicatorAlertRule, rule_id).last_fired_at is None

    def test_disabled_and_expired_window(self, alert_db):
        ind_id = _seed_indicator(alert_db)
        disabled_id = _seed_rule(alert_db, ind_id, enabled=False)
        executor = FakeExecutor([{"name": "ma", "data": [0.0, 999.0]}])
        fetch = lambda rule: _bars()  # noqa: E731

        assert alerts.run_evaluation_round(executor=executor, fetch_kline=fetch) == []

        # 去重窗口过期后重新触发：手动把 last_fired_at 拨回 40 分钟前（> frequency 30）
        expired_id = _seed_rule(alert_db, ind_id)
        with alert_db() as db:
            row = db.get(IndicatorAlertRule, expired_id)
            row.last_fired_at = alerts.utc_now() - timedelta(minutes=40)
            db.commit()

        triggers = alerts.run_evaluation_round(executor=executor, fetch_kline=fetch)
        assert {t["rule"]["id"] for t in triggers} == {expired_id}
        assert disabled_id not in {t["rule"]["id"] for t in triggers}

    def test_missing_indicator_skipped(self, alert_db):
        _seed_rule(alert_db, 999999)
        executor = FakeExecutor([{"name": "ma", "data": [0.0, 999.0]}])
        assert alerts.run_evaluation_round(executor=executor, fetch_kline=lambda rule: _bars()) == []

    def test_insufficient_plot_data(self, alert_db):
        ind_id = _seed_indicator(alert_db)
        _seed_rule(alert_db, ind_id)
        executor = FakeExecutor([{"name": "ma", "data": [110.0]}])  # 只有一根，cross/比较不足
        assert alerts.run_evaluation_round(executor=executor, fetch_kline=lambda rule: _bars()) == []

    def test_empty_bars(self, alert_db):
        ind_id = _seed_indicator(alert_db)
        _seed_rule(alert_db, ind_id)
        executor = FakeExecutor([{"name": "ma", "data": [110.0, 120.0]}])
        assert alerts.run_evaluation_round(executor=executor, fetch_kline=lambda rule: []) == []


@pytest.fixture()
def alert_client(alert_db, monkeypatch):
    """仅挂 alerts 路由的 TestClient，guest 判定固定放行。"""
    from indicators import alerts_routes

    monkeypatch.setattr(alerts_routes, "is_guest_user", lambda request: False)
    app = FastAPI()
    app.include_router(alerts_routes.router)
    return TestClient(app, raise_server_exceptions=False)


class TestAlertRoutes:
    def _payload(self, indicator_id: int) -> dict:
        return {
            "indicator_id": indicator_id,
            "name": "MA 越界提醒",
            "symbol": "btcusdt",
            "period": "1h",
            "op": "gt",
            "threshold": 100.0,
            "channels": ["websocket"],
        }

    def test_crud_roundtrip(self, alert_db, alert_client):
        ind_id = _seed_indicator(alert_db)
        resp = alert_client.post("/api/v1/indicators/alerts", json=self._payload(ind_id))
        assert resp.status_code == 200
        rule = resp.json()["data"]
        assert rule["id"] > 0
        assert rule["symbol"] == "BTCUSDT"  # 统一大写存储

        # 列表按 indicator_id 过滤
        listed = alert_client.get("/api/v1/indicators/alerts", params={"indicator_id": ind_id}).json()["data"]
        assert [r["id"] for r in listed] == [rule["id"]]

        # 更新：暂停
        updated = alert_client.put(f"/api/v1/indicators/alerts/{rule['id']}", json={"enabled": False})
        assert updated.json()["data"]["enabled"] is False

        # 删除后 404
        assert alert_client.delete(f"/api/v1/indicators/alerts/{rule['id']}").status_code == 200
        assert alert_client.delete(f"/api/v1/indicators/alerts/{rule['id']}").status_code == 404

    def test_create_validates(self, alert_db, alert_client):
        # 指标不存在 → 404
        assert alert_client.post("/api/v1/indicators/alerts", json=self._payload(999999)).status_code == 404

        ind_id = _seed_indicator(alert_db)
        # 非法 op / 渠道 / 周期字段 → 422
        bad_op = self._payload(ind_id) | {"op": "greater"}
        assert alert_client.post("/api/v1/indicators/alerts", json=bad_op).status_code == 422
        bad_ch = self._payload(ind_id) | {"channels": ["sms"]}
        assert alert_client.post("/api/v1/indicators/alerts", json=bad_ch).status_code == 400
        bad_symbol = self._payload(ind_id) | {"symbol": ""}
        assert alert_client.post("/api/v1/indicators/alerts", json=bad_symbol).status_code == 422

    def test_update_unknown_rule_404(self, alert_client):
        assert alert_client.put("/api/v1/indicators/alerts/999", json={"enabled": False}).status_code == 404

    def test_alerts_not_shadowed_by_detail_route(self, alert_db, monkeypatch):
        """回归守护（main.py 路由挂载顺序）：

        indicators_router 的 GET /{indicator_id} 若先于 alerts_router 挂载，
        会把 /api/v1/indicators/alerts 当作 indicator_id 吞掉（int("alerts") 失败 → 422）。
        这里复刻 main.py 的真实顺序挂载两个 router，断言列表端点正常命中。
        """
        from indicators import alerts_routes
        from indicators import routes as indicator_routes

        monkeypatch.setattr(alerts_routes, "is_guest_user", lambda request: False)
        monkeypatch.setattr(indicator_routes, "is_guest_user", lambda request: False)
        app = FastAPI()
        # 顺序必须与 main.py 一致：alerts 在前
        app.include_router(alerts_routes.router)
        app.include_router(indicator_routes.router)
        client = TestClient(app, raise_server_exceptions=False)

        ind_id = _seed_indicator(alert_db)
        rule_id = _seed_rule(alert_db, ind_id)

        # 422 复现路径：GET /api/v1/indicators/alerts?indicator_id=5 被 GET /{indicator_id} 吞掉
        resp = client.get("/api/v1/indicators/alerts", params={"indicator_id": ind_id})
        assert resp.status_code == 200
        assert [r["id"] for r in resp.json()["data"]] == [rule_id]

        # 挂载顺序调整不得破坏 indicators 自身路由
        assert client.get(f"/api/v1/indicators/{ind_id}").status_code == 200

    def test_preview_send_semantics(self, alert_db, alert_client, monkeypatch):
        """预演端点：send=false 仅返回消息预览不投递；send=true 才按所选渠道真实发送。"""
        from indicators import alerts_routes as ar

        ind_id = _seed_indicator(alert_db)
        monkeypatch.setattr(
            ar, "IndicatorExecutor", lambda timeout=None: FakeExecutor([{"name": "ma", "data": [90.0, 110.0]}])
        )
        monkeypatch.setattr(ar.alerts, "fetch_kline_bars", lambda rule: _bars())

        sent: list[dict] = []

        async def fake_send(**kwargs):
            sent.append(kwargs)
            return {"success": True, "channel_results": {}}

        monkeypatch.setattr(ar.notification_service, "send_notification", fake_send)

        # send=false：纯预览，评估+组装文案，不发送
        resp = alert_client.post(
            "/api/v1/indicators/alerts/preview",
            json={"rule": self._payload(ind_id), "send": False},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["evaluation"]["triggered"] is True
        assert data["evaluation"]["value"] == 110.0
        assert "MA 越界提醒" in data["preview"]["title"]
        assert "110" in data["preview"]["content"]
        assert "send_result" not in data
        assert sent == []

        # send=true：真实投递，标题带 [测试] 前缀
        resp = alert_client.post(
            "/api/v1/indicators/alerts/preview",
            json={"rule": self._payload(ind_id), "send": True},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["send_result"]["success"] is True
        assert len(sent) == 1
        assert sent[0]["title"].startswith("[测试]")
        assert [c.value for c in sent[0]["channels"]] == ["websocket"]

        # 指标不存在 → 404
        missing = self._payload(999999)
        assert (
            alert_client.post("/api/v1/indicators/alerts/preview", json={"rule": missing, "send": False}).status_code
            == 404
        )

    def test_test_send_forces_notification(self, alert_db, alert_client, monkeypatch):
        from indicators import alerts_routes as ar

        ind_id = _seed_indicator(alert_db)
        rule_id = _seed_rule(alert_db, ind_id)
        # CustomIndicatorBusiness.get_code 统一走 db_module.SessionLocal，alert_db fixture 已替换，无需再补丁

        sent: dict = {}

        async def fake_send(**kwargs):
            sent.update(kwargs)
            return {"success": True, "channel_results": {}}

        monkeypatch.setattr(ar.notification_service, "send_notification", fake_send)
        monkeypatch.setattr(
            ar, "IndicatorExecutor", lambda timeout=None: FakeExecutor([{"name": "ma", "data": [90.0, 110.0]}])
        )
        monkeypatch.setattr(ar.alerts, "fetch_kline_bars", lambda rule: _bars())

        resp = alert_client.post(f"/api/v1/indicators/alerts/{rule_id}/test")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["evaluation"]["triggered"] is True
        assert sent["level"].value == "warning"
        assert sent["category"].value == "alert"
        assert [c.value for c in sent["channels"]] == ["websocket"]

        # 测试发送不去重：last_fired_at 保持空
        with alert_db() as db:
            assert db.get(IndicatorAlertRule, rule_id).last_fired_at is None
