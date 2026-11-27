"""fetch_recent_klines / GET /marketdata/klines 单测（spec §1）。

复用 test_latest_price.py 的 FakeSession 模式（照抄其 stub 手法）：
- 服务层：monkeypatch 用 FakeSession 顶替 aiohttp.ClientSession，resolve_proxy 置 None。
- 路由层：TestClient 只挂 marketdata router，monkeypatch service.fetch_recent_klines。
"""

import asyncio

import aiohttp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from marketdata import routes, service


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload


def _patch_session(monkeypatch, script: list):
    """假 ClientSession 顶替 aiohttp：script 依次弹出 payload 或 Exception。
    返回 calls 记录（url/params/proxy），供断言打到哪个 endpoint、带了什么查询参数。"""
    calls: list = []

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def get(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            item = script.pop(0)
            if isinstance(item, Exception):
                raise item
            return _FakeResponse(item)

    monkeypatch.setattr(service.aiohttp, "ClientSession", _FakeSession)
    # 测试环境不解析真实代理，回源行为与代理取值无关
    monkeypatch.setattr(service, "resolve_proxy", lambda: None)
    return calls


# 币安 K 线原生行：[open_time, open, high, low, close, volume, ...]（时间升序）
_ROW_A = [1700000000000, "100", "110", "90", "120", "1"]
_ROW_B = [1700000090000, "120", "130", "115", "125", "2"]


# ---------------------------------------------------------------------------
# 服务层 fetch_recent_klines
# ---------------------------------------------------------------------------


def test_fetch_recent_klines_payload_contract(monkeypatch):
    """原生行数组 → [{ts,open,high,low,close,volume}]；ts 毫秒原样透传、不加排序"""
    calls = _patch_session(monkeypatch, [[_ROW_A, _ROW_B]])

    result = asyncio.run(service.fetch_recent_klines("btc/usdt", "spot", "binance"))

    assert result == [
        {"ts": 1700000000000, "open": 100.0, "high": 110.0, "low": 90.0, "close": 120.0, "volume": 1.0},
        {"ts": 1700000090000, "open": 120.0, "high": 130.0, "low": 115.0, "close": 125.0, "volume": 2.0},
    ]
    assert calls[0]["url"] == service.SPOT_KLINES_URL
    assert calls[0]["params"]["symbol"] == "BTCUSDT"
    assert calls[0]["params"]["interval"] == "15m"


def test_fetch_recent_klines_market_type_split(monkeypatch):
    """market_type 分流：futures → fapi.binance.com；spot/margin 复用现货 endpoint"""
    calls = _patch_session(monkeypatch, [[_ROW_A]])
    asyncio.run(service.fetch_recent_klines("BTCUSDT", "futures", "binance"))
    assert calls[0]["url"] == service.FUTURES_KLINES_URL

    calls_margin = _patch_session(monkeypatch, [[_ROW_A]])
    asyncio.run(service.fetch_recent_klines("BTCUSDT", market_type="margin", exchange="binance"))
    assert calls_margin[0]["url"] == service.SPOT_KLINES_URL


def test_fetch_recent_klines_bad_interval():
    """interval 不在白名单 → ValueError（路由层映射 422）"""
    with pytest.raises(ValueError):
        asyncio.run(service.fetch_recent_klines("BTCUSDT", "spot", "binance", interval="3m"))


def test_fetch_recent_klines_limit_clamp(monkeypatch):
    """limit clamp：None→120；>500→500；<1→1"""
    calls = _patch_session(monkeypatch, [[_ROW_A], [_ROW_A], [_ROW_A]])

    asyncio.run(service.fetch_recent_klines("BTCUSDT", "spot", "binance", limit=None))
    asyncio.run(service.fetch_recent_klines("BTCUSDT", "spot", "binance", limit=1000))
    asyncio.run(service.fetch_recent_klines("BTCUSDT", "spot", "binance", limit=0))

    assert [c["params"]["limit"] for c in calls] == [120, 500, 1]


def test_fetch_recent_klines_unsupported_exchange():
    """未支持的交易所 → UnsupportedExchangeError（路由层转 400），不回源不降级"""
    with pytest.raises(service.UnsupportedExchangeError):
        asyncio.run(service.fetch_recent_klines("BTCUSDT", "spot", "okx"))


def test_fetch_recent_klines_unsupported_market_type():
    with pytest.raises(service.UnsupportedExchangeError):
        asyncio.run(service.fetch_recent_klines("BTCUSDT", "options", "binance"))


def test_fetch_recent_klines_source_failure(monkeypatch):
    """回源异常原样上抛（路由层映射 502），失败不缓存无残留"""
    _patch_session(monkeypatch, [aiohttp.ClientError("connection refused")])

    with pytest.raises(aiohttp.ClientError):
        asyncio.run(service.fetch_recent_klines("BTCUSDT", "spot", "binance"))


# ---------------------------------------------------------------------------
# 路由层 GET /api/v1/marketdata/klines
# ---------------------------------------------------------------------------


def test_klines_endpoint_returns_envelope(monkeypatch):
    async def fake_fetch(symbol, market_type="spot", exchange="binance", interval="15m", limit=None):
        return [{"ts": 1700000000000, "open": 100.0, "high": 110.0, "low": 90.0, "close": 120.0, "volume": 1.0}]

    monkeypatch.setattr(service, "fetch_recent_klines", fake_fetch)
    resp = _client().get(
        "/api/v1/marketdata/klines",
        params={"symbol": "BTCUSDT", "market_type": "futures", "exchange": "binance", "interval": "1h"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"][0]["ts"] == 1700000000000


def test_klines_endpoint_maps_unreachable_to_502(monkeypatch):
    """回源失败 → 502 + detail.code=exchange_unreachable"""

    async def boom(*args, **kwargs):
        raise RuntimeError("connect timeout")

    monkeypatch.setattr(service, "fetch_recent_klines", boom)
    resp = _client().get("/api/v1/marketdata/klines", params={"symbol": "BTCUSDT"})

    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "exchange_unreachable"


def test_klines_endpoint_maps_unsupported_to_400(monkeypatch):
    """未支持的交易所 → 400 + detail.code=unsupported_exchange"""

    async def bad_exchange(*args, **kwargs):
        raise service.UnsupportedExchangeError("暂不支持交易所 okx 的K线行情")

    monkeypatch.setattr(service, "fetch_recent_klines", bad_exchange)
    resp = _client().get("/api/v1/marketdata/klines", params={"symbol": "BTCUSDT", "exchange": "okx"})

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unsupported_exchange"


def test_klines_endpoint_maps_bad_interval_to_422(monkeypatch):
    """interval 白名单越界 → 422"""

    async def bad_interval(*args, **kwargs):
        raise ValueError("不支持的K线周期: 3m")

    monkeypatch.setattr(service, "fetch_recent_klines", bad_interval)
    resp = _client().get("/api/v1/marketdata/klines", params={"symbol": "BTCUSDT", "interval": "3m"})

    assert resp.status_code == 422
