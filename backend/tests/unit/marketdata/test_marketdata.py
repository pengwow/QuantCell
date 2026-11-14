"""marketdata 路由信封与降级行为（service 层 monkeypatch，不真连网）。"""

import asyncio

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from marketdata import service
from marketdata.routes import router


def _client() -> TestClient:
    """轻量 app：只挂 marketdata router，不引 main.py 的全部路由与中间件。"""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _patch_service_ok(monkeypatch):
    """三个 service async 函数换成契约 shape 的 fake，完全跳过 aiohttp。"""

    async def fake_depth(symbol, limit):
        return {
            "symbol": symbol.replace("/", "").upper(),
            "bids": [[60000.0, 1.0]],
            "asks": [[60001.0, 2.0]],
            "timestamp": 1700000000000,
        }

    async def fake_oi(symbol, interval, limit):
        return [
            {"timestamp": 1700000000000 + i * 300000, "openInterest": 123.4, "openInterestValue": 5678.9}
            for i in range(min(limit, 3))
        ]

    async def fake_funding(symbol, limit):
        return [{"timestamp": 1700000000000 + i * 8 * 3600 * 1000, "fundingRate": 0.0001} for i in range(min(limit, 3))]

    monkeypatch.setattr(service, "fetch_depth_snapshot", fake_depth)
    monkeypatch.setattr(service, "fetch_oi_history", fake_oi)
    monkeypatch.setattr(service, "fetch_funding_history", fake_funding)
    return fake_oi, fake_funding


def test_depth_returns_envelope_and_normalized_symbol(monkeypatch):
    _patch_service_ok(monkeypatch)
    resp = _client().get("/api/v1/marketdata/depth", params={"symbol": "btcusdt", "limit": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["symbol"] == "BTCUSDT"  # service 归一化大写
    assert isinstance(body["data"]["timestamp"], int)


def test_depth_limit_out_of_range_rejected(monkeypatch):
    _patch_service_ok(monkeypatch)
    client = _client()
    # 下限 ge=5：limit=1 被参数校验拦截（Pydantic/FastAPI 兜）
    assert client.get("/api/v1/marketdata/depth", params={"symbol": "BTCUSDT", "limit": 1}).status_code == 422
    # 上限 le=50
    assert client.get("/api/v1/marketdata/depth", params={"symbol": "BTCUSDT", "limit": 51}).status_code == 422


def test_upstream_failure_maps_to_502(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(service, "fetch_depth_snapshot", boom)
    monkeypatch.setattr(service, "fetch_oi_history", boom)
    monkeypatch.setattr(service, "fetch_funding_history", boom)
    client = _client()
    assert client.get("/api/v1/marketdata/depth", params={"symbol": "BTCUSDT"}).status_code == 502
    assert client.get("/api/v1/marketdata/oi/history", params={"symbol": "BTCUSDT"}).status_code == 502
    assert client.get("/api/v1/marketdata/funding/history", params={"symbol": "BTCUSDT"}).status_code == 502


def test_oi_funding_route_shapes(monkeypatch):
    _patch_service_ok(monkeypatch)
    client = _client()
    oi = client.get("/api/v1/marketdata/oi/history", params={"symbol": "BTCUSDT", "interval": "15m"})
    assert oi.status_code == 200
    assert isinstance(oi.json()["data"], list)
    assert all(isinstance(row["timestamp"], int) for row in oi.json()["data"])
    funding = client.get("/api/v1/marketdata/funding/history", params={"symbol": "BTCUSDT", "limit": 10})
    assert funding.status_code == 200
    assert isinstance(funding.json()["data"], list)
    assert all(isinstance(row["timestamp"], int) for row in funding.json()["data"])


def test_service_oi_column_mapping(monkeypatch):
    """service 层直测：binance 原始列（字符串值）→ 契约字段，tail(limit) 截取。"""
    captured: dict = {}

    class FakeFetcher:
        def __init__(self, market="um", interval="1h"):
            captured["market"], captured["interval"] = market, interval

        async def fetch(self, session, symbol, start_ms, end_ms):
            captured["symbol"], captured["window"] = symbol, (start_ms, end_ms)
            return pd.DataFrame(
                [
                    {
                        # openInterestHist 原始条目：数值列均为字符串
                        "symbol": "BTCUSDT",
                        "sumOpenInterest": str(100 + i),
                        "sumOpenInterestValue": str(1000.5 + i),
                        "timestamp": 1700000000000 + i * 300000,
                    }
                    for i in range(200)  # 超过 limit=96，验证 tail 截取
                ]
            )

    monkeypatch.setattr(service, "OpenInterestFetcher", FakeFetcher)
    rows = asyncio.run(service.fetch_oi_history("BTC/USDT", "15m", 96))
    assert captured["market"] == "um"
    assert captured["interval"] == "15m"
    assert captured["symbol"] == "BTCUSDT"
    # start < end 的 30 天窗口顺序正确
    assert captured["window"][0] < captured["window"][1]
    assert len(rows) == 96
    assert rows[-1]["timestamp"] == 1700000000000 + 199 * 300000
    for row in rows:
        assert isinstance(row["timestamp"], int)
        assert isinstance(row["openInterest"], float)  # USD 口径取 sumOpenInterestValue
        assert isinstance(row["openInterestValue"], float)


def test_service_funding_column_mapping(monkeypatch):
    """service 层直测：fundingRate 原始为字符串 → float；tail(limit) 截取。"""
    captured: dict = {}

    class FakeFetcher:
        def __init__(self, market="um"):
            captured["market"] = market

        async def fetch(self, session, symbol, start_ms, end_ms):
            captured["symbol"] = symbol
            return pd.DataFrame(
                [
                    {
                        "symbol": "BTCUSDT",
                        "timestamp": 1700000000000 + i * 8 * 3600 * 1000,
                        "fundingRate": str(0.0001 * (i % 3 - 1)),  # 币安原始返回字符串
                    }
                    for i in range(50)  # 超过 limit=42
                ]
            )

    monkeypatch.setattr(service, "FundingRateFetcher", FakeFetcher)
    rows = asyncio.run(service.fetch_funding_history("BTCUSDT", 42))
    assert captured["market"] == "um"
    assert captured["symbol"] == "BTCUSDT"
    assert len(rows) == 42
    for row in rows:
        assert isinstance(row["timestamp"], int)
        assert isinstance(row["fundingRate"], float)
