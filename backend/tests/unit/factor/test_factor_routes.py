"""因子分析 HTTP 端到端检查（TestClient，走真实 crypto parquet）。

覆盖 service 之外的路由层关键点：
- 认证依赖可被覆盖，路由真实挂载在 /api/v1/factor
- analyze 全链路取数→计算→JSON 可序列化（numpy 经 _sanitize）
- 时间戳按真实单位解析，序列日期不得落在 1970 年
- instruments 扫描 crypto/spot/klines 布局

仅当本地存在 BTCUSDT 1h 数据时运行，否则模块级 skip（无数据环境/CI 不报错）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from utils import get_source_data_dir
from utils.auth import get_current_user

_DATA = get_source_data_dir() / "crypto" / "spot" / "klines" / "1h" / "BTCUSDT.parquet"
if not _DATA.exists():
    pytest.skip("本地无 BTCUSDT 1h parquet，跳过 HTTP 端到端检查", allow_module_level=True)

from main import app  # 在 skip 判定之后导入，避免无数据环境强制装配整个应用


def _client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {"username": "e2e", "id": 1}
    return TestClient(app)


def test_instruments_lists_crypto_klines():
    client = _client()
    try:
        resp = client.get("/api/v1/factor/instruments", params={"candle_type": "spot"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    symbols = {item["symbol"]: item["intervals"] for item in body["data"]["symbols"]}
    assert "BTCUSDT" in symbols
    assert "1h" in symbols["BTCUSDT"]


def test_analyze_end_to_end_payload():
    client = _client()
    try:
        resp = client.post(
            "/api/v1/factor/analyze",
            json={
                "factor_name": "close",
                "instruments": ["BTCUSDT"],
                "interval": "1h",
                "candle_type": "spot",
                "start_time": None,
                "end_time": None,
                "method": "spearman",
                "n_groups": 5,
                "window": 20,
                "forward": 1,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    data = body["data"]

    assert data["bar_count"] >= 22
    assert len(data["groups"]) == 5
    assert data["long_short_return"] is not None

    # 时间戳单位正确：日期必须是 2020 年代，而不是被当成纳秒的 1970 年
    dates = data["series"]["dates"]
    assert dates and dates[0].startswith("202")

    # 前端工作台契约：factor 按日期键取值、close 是与 dates 等长的有序列表
    factor_map = data["series"]["factor"]
    close_list = data["series"]["close"]
    assert isinstance(factor_map, dict) and len(factor_map) == len(dates)
    assert isinstance(close_list, list) and len(close_list) == len(dates)
    assert factor_map[dates[0]] is not None

    # IC 序列时间标签同样不得落到 1970 年
    ic_series = [p for p in data["ic"]["series"] if p["ic"] is not None]
    assert ic_series and ic_series[0]["t"].startswith("202")
