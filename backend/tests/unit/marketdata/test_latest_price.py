"""marketdata 实时价格（fetch_latest_price + GET /price）单元测试。

测试策略：
- 服务层：monkeypatch 用 FakeSession 顶替 aiohttp.ClientSession（script 依次回放
  payload 或异常），resolve_proxy 置 None，不打真实网络。
- 路由层：TestClient 只挂 marketdata router（轻量 app），monkeypatch
  service.fetch_latest_price 隔离网络。
"""

import asyncio

import aiohttp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from marketdata import routes, service


@pytest.fixture(autouse=True)
def _clear_price_cache():
    """fetch_latest_price 的微缓存是模块级 dict，用例间必须清空，否则互相污染"""
    service._PRICE_CACHE.clear()
    yield
    service._PRICE_CACHE.clear()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


class _FakeResponse:
    def __init__(self, payload: dict):
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
    """用假 ClientSession 顶替 aiohttp：script 依次弹出 payload 或 Exception。
    返回 calls 记录（url/params/proxy），供断言打了几次交易所、打到哪个 endpoint。"""
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


# ---------------------------------------------------------------------------
# 服务层 fetch_latest_price
# ---------------------------------------------------------------------------


def test_fetch_latest_price_spot_contract(monkeypatch):
    """现货回源 api.binance.com，symbol 归一化，响应契约 symbol/price/ts"""
    calls = _patch_session(monkeypatch, [{"symbol": "BTCUSDT", "price": "68000.5"}])

    result = asyncio.run(service.fetch_latest_price("btc/usdt", "spot", "binance"))

    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == 68000.5
    # 项目时间戳规范：ISO 8601 纳秒精度（小数段 9 位 + "+00:00" 后缀）
    assert result["ts"].endswith("+00:00")
    assert len(result["ts"].split(".")[1]) == 9 + len("+00:00")
    assert calls[0]["url"] == service.SPOT_TICKER_URL


def test_fetch_latest_price_futures_uses_fapi(monkeypatch):
    """futures 回源 fapi.binance.com（与现货不同 endpoint，缓存 key 也不同）"""
    calls = _patch_session(monkeypatch, [{"symbol": "BTCUSDT", "price": "1"}])

    asyncio.run(service.fetch_latest_price("BTCUSDT", "futures", "binance"))

    assert calls[0]["url"] == service.FUTURES_TICKER_URL


def test_fetch_latest_price_hit_cache_within_ttl(monkeypatch):
    """30s 内同 (exchange|symbol|market_type) 第二次调用不再打交易所"""
    calls = _patch_session(
        monkeypatch,
        [{"symbol": "BTCUSDT", "price": "1"}, {"symbol": "BTCUSDT", "price": "2"}],
    )

    first = asyncio.run(service.fetch_latest_price("BTCUSDT", "spot", "binance"))
    second = asyncio.run(service.fetch_latest_price("BTCUSDT", "spot", "binance"))

    assert len(calls) == 1
    assert first == second


def test_fetch_latest_price_failure_not_cached(monkeypatch):
    """失败不进缓存：第一次网络异常、重试第二次成功，交易所被打两次"""
    calls = _patch_session(
        monkeypatch,
        [aiohttp.ClientError("connection refused"), {"symbol": "BTCUSDT", "price": "1"}],
    )

    with pytest.raises(aiohttp.ClientError):
        asyncio.run(service.fetch_latest_price("BTCUSDT", "spot", "binance"))

    result = asyncio.run(service.fetch_latest_price("BTCUSDT", "spot", "binance"))

    assert len(calls) == 2
    assert result["price"] == 1.0


def test_fetch_latest_price_unsupported_exchange():
    """未支持的交易所直接抛 UnsupportedExchangeError（路由层转 400），不回源不降级"""
    with pytest.raises(service.UnsupportedExchangeError):
        asyncio.run(service.fetch_latest_price("BTCUSDT", "spot", "okx"))


def test_fetch_latest_price_unsupported_market_type():
    with pytest.raises(service.UnsupportedExchangeError):
        asyncio.run(service.fetch_latest_price("BTCUSDT", "options", "binance"))
