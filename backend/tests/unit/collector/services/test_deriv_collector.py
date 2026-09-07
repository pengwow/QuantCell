"""collector.services.deriv_collector 单元测试。

覆盖衍生数据采集器：
- DerivCollector._parse_time_range / _build_save_dir 纯逻辑
- FundingRateFetcher.fetch: 分页拉取、URL 按 market 切换、空数据处理
- OpenInterestFetcher.fetch: 持仓量数据 + 时间戳注入
（网络层通过 FakeSession 模拟 aiohttp，不发起真实请求）
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from collector.services.deriv_collector import (
    DerivCollector,
    FundingRateFetcher,
    OpenInterestFetcher,
    _market_from_str,
)


class FakeResp:
    """模拟 aiohttp 响应对象"""

    def __init__(self, payload):
        self._payload = payload

    async def raise_for_status(self):
        return None

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    """模拟 aiohttp.ClientSession, 按序消费预设响应

    注意：aiohttp 的 session.get() 是同步方法，返回实现了异步上下文管理协议
    (__aenter__/__aexit__) 的对象，因此这里用同步 def + FakeResp 来模拟。
    使用 async def get 会返回协程，`async with` 无法直接使用。
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.last_url = None
        self.last_params = None
        self.proxy = None

    def get(self, url, params=None, **kwargs):
        self.last_url = url
        self.last_params = params
        self.proxy = kwargs.get("proxy")
        payload = self._responses.pop(0) if self._responses else []
        return FakeResp(payload)


# =================== 工具/纯逻辑 ===================


def test_market_from_str():
    assert _market_from_str("um") == "um"
    assert _market_from_str("cm") == "cm"


class TestDerivCollectorLogic:
    def test_parse_time_range_none(self):
        start_ms, end_ms = DerivCollector()._parse_time_range(None, None)
        assert start_ms is None
        assert end_ms is None

    def test_parse_time_range_with_dates(self):
        start_ms, end_ms = DerivCollector()._parse_time_range("2024-01-01", "2024-01-02")
        expected_start = int(datetime.strptime("2024-01-01", "%Y-%m-%d").timestamp() * 1000)
        expected_end = int(datetime.strptime("2024-01-02", "%Y-%m-%d").timestamp() * 1000)
        assert start_ms == expected_start
        assert end_ms == expected_end

    def test_build_save_dir_creates_nested(self, tmp_path):
        save_dir = DerivCollector(base_dir=str(tmp_path))._build_save_dir("fundingRate", "um", "BTCUSDT")
        assert save_dir == tmp_path / "fundingRate" / "um" / "BTCUSDT"
        assert save_dir.is_dir()


# =================== FundingRateFetcher ===================


class TestFundingRateFetcher:
    def test_fetch_single_page_renames_timestamp(self):
        payload = [{"symbol": "BTCUSDT", "fundingTime": 1704067200000, "fundingRate": "0.0001"}]
        session = FakeSession([payload])
        df = run_async(FundingRateFetcher(market="um").fetch(session, "BTCUSDT"))
        assert isinstance(df, pd.DataFrame)
        assert "timestamp" in df.columns
        assert "fundingTime" not in df.columns
        assert df.iloc[0]["timestamp"] == 1704067200000

    def test_fetch_empty_returns_empty_df(self):
        df = run_async(FundingRateFetcher(market="um").fetch(FakeSession([[]]), "BTCUSDT"))
        assert df.empty

    def test_fetch_paginates_and_advances_start_time(self):
        # 第一页返回 1000 条（达到 limit 触发翻页），第二页返回空 -> 停止
        page1 = [{"symbol": "BTCUSDT", "fundingTime": 1704067200000 + i, "fundingRate": "0.0001"} for i in range(1000)]
        session = FakeSession([page1, []])
        df = run_async(FundingRateFetcher(market="um").fetch(session, "BTCUSDT"))
        assert len(df) == 1000
        # 翻页后 startTime 应推进到最后一条 fundingTime + 1
        assert session.last_params["startTime"] == 1704067200000 + 999 + 1
        assert session.last_params["limit"] == 1000

    def test_fetch_stops_when_partial_page(self):
        page1 = [{"symbol": "BTCUSDT", "fundingTime": 1704067200000 + i, "fundingRate": "0.0001"} for i in range(500)]
        session = FakeSession([page1])
        df = run_async(FundingRateFetcher(market="um").fetch(session, "BTCUSDT"))
        assert len(df) == 500

    def test_fetch_cm_uses_dapi_url(self):
        session = FakeSession([[{"fundingTime": 1, "fundingRate": "0.0"}]])
        fetcher = FundingRateFetcher(market="cm")
        run_async(fetcher.fetch(session, "BTCUSD"))
        assert session.last_url.endswith("/dapi/v1/fundingRate")


# =================== OpenInterestFetcher ===================


class TestOpenInterestFetcher:
    def test_fetch_adds_nanosecond_timestamp(self):
        payload = {
            "symbol": "BTCUSDT",
            "openInterest": "12345.6",
            "openInterestValue": "987654321.1",
        }
        session = FakeSession([payload])
        df = run_async(OpenInterestFetcher(market="um").fetch(session, "BTCUSDT"))
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "BTCUSDT"
        # 注入的 timestamp 应为纳秒级整数
        assert df.iloc[0]["timestamp"] >= 1_700_000_000_000_000_000

    def test_fetch_empty_returns_empty_df(self):
        df = run_async(OpenInterestFetcher(market="um").fetch(FakeSession([{}]), "BTCUSDT"))
        assert df.empty

    def test_fetch_cm_url(self):
        session = FakeSession([{"symbol": "BTCUSD", "openInterest": "1"}])
        df = run_async(OpenInterestFetcher(market="cm").fetch(session, "BTCUSD"))
        assert session.last_url.endswith("/dapi/v1/openInterest")
        assert len(df) == 1


def run_async(coro):
    """同步运行一个 asyncio coroutine"""
    import asyncio

    return asyncio.run(coro)
