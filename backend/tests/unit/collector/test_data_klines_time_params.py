"""/data/klines 时间参数与 order 校验测试

行情回放依赖毫秒时间戳分块取数；非法时间必须显式 400，禁止静默忽略过滤条件。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from collector.api import data as data_api
from collector.api.data import router
from collector.db.database import get_db


class StubDataService:
    """捕获 get_kline_data 透传参数，返回固定成功结果"""

    last_kwargs: dict | None = None

    def __init__(self, db):
        pass

    def get_kline_data(self, **kwargs):
        StubDataService.last_kwargs = kwargs
        return {"success": True, "message": "ok", "kline_data": []}


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def setup_function(_):
    StubDataService.last_kwargs = None
    data_api.DataService = StubDataService


def test_invalid_start_time_returns_400():
    client = make_client()
    resp = client.get(
        "/data/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "start_time": "not-a-date"},
    )
    assert resp.status_code == 400
    assert "开始时间" in resp.json()["detail"]


def test_invalid_end_time_returns_400():
    client = make_client()
    resp = client.get(
        "/data/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "end_time": "2024/01/01"},
    )
    assert resp.status_code == 400
    assert "结束时间" in resp.json()["detail"]


def test_millisecond_timestamp_accepted_and_passed_through():
    client = make_client()
    resp = client.get(
        "/data/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "start_time": 1704067200000},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    # 纯数字 query 值到达 service 时可能是 int 或数字字符串，factory 侧两种都按毫秒换算
    assert int(StubDataService.last_kwargs["start_time"]) == 1704067200000


def test_order_asc_and_desc_passed_through():
    client = make_client()
    resp = client.get(
        "/data/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "order": "asc"},
    )
    assert resp.status_code == 200
    assert StubDataService.last_kwargs["order"] == "asc"

    resp = client.get("/data/klines", params={"symbol": "BTCUSDT", "interval": "1h"})
    assert resp.status_code == 200
    assert StubDataService.last_kwargs["order"] == "desc"


def test_invalid_order_rejected():
    client = make_client()
    resp = client.get(
        "/data/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "order": "middle"},
    )
    assert resp.status_code == 422
