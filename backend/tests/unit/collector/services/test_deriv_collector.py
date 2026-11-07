"""collector.services.deriv_collector 单元测试。

覆盖衍生数据采集器：
- DerivCollector._parse_time_range / _build_save_dir 纯逻辑
- to_storage_symbol / to_api_symbol 符号规范化
- FundingRateFetcher.fetch: 分页拉取、URL 按 market 切换、空数据处理
- OpenInterestFetcher.fetch: um 历史序列端点(分页/30天裁剪/period映射)、cm 快照列名对齐
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
    to_api_symbol,
    to_storage_symbol,
)


class FakeResp:
    """模拟 aiohttp 响应对象"""

    def __init__(self, payload):
        self._payload = payload

    # aiohttp 的 ClientResponse.raise_for_status 是同步方法，与业务侧
    # 调用约定一致（用 async 定义会产生 never-awaited 协程告警）
    def raise_for_status(self):
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
    def test_um_hist_returns_contract_columns(self):
        # um 走 openInterestHist 历史端点, 行由交易所提供 timestamp(ms)
        payload = [
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "100.5",
                "sumOpenInterestValue": "9900000",
                "timestamp": 1704067200000,
            },
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "101.0",
                "sumOpenInterestValue": "9950000",
                "timestamp": 1704070800000,
            },
        ]
        session = FakeSession([payload])
        df = run_async(OpenInterestFetcher(market="um", interval="1h").fetch(session, "BTCUSDT"))
        assert session.last_url.endswith("/futures/data/openInterestHist")
        assert len(df) == 2
        assert list(df.columns) == ["symbol", "sumOpenInterest", "sumOpenInterestValue", "timestamp"]
        assert df.iloc[0]["timestamp"] == 1704067200000

    def test_um_hist_period_map_and_interval(self):
        fetcher = OpenInterestFetcher(market="um", interval="15m")
        assert fetcher.period == "15m"
        assert OpenInterestFetcher(market="um", interval="1m").period == "5m"
        assert OpenInterestFetcher(market="um", interval="8h").period == "6h"
        assert OpenInterestFetcher(market="um", interval="1w").period == "1d"

    def test_um_hist_paginates(self):
        # 满页 500 条 -> 触发翻页推进 startTime, 第二页部分行 -> 停止
        base = 1704067200000

        def page(start, n):
            return [
                {
                    "symbol": "BTCUSDT",
                    "sumOpenInterest": "1",
                    "sumOpenInterestValue": "1",
                    "timestamp": start + i * 3_600_000,
                }
                for i in range(n)
            ]

        session = FakeSession([page(base, 500), page(base + 500 * 3_600_000, 3)])
        df = run_async(OpenInterestFetcher(market="um", interval="1h").fetch(session, "BTCUSDT"))
        assert len(df) == 503
        # startTime 推进到最后一条 timestamp + 1ms
        assert session.last_params["startTime"] == base + 499 * 3_600_000 + 1

    def test_um_hist_clamps_to_30d_lookback(self):
        # start 早于 30 天上限 -> 裁剪: startTime 参数应为 now - 30d
        session = FakeSession([[]])
        run_async(OpenInterestFetcher(market="um", interval="1h").fetch(session, "BTCUSDT", start_time=0))
        now_ms = int(datetime.now().timestamp() * 1000)
        expected = now_ms - OpenInterestFetcher.MAX_LOOKBACK_MS
        # 裁剪发生于 now_ms 取值之前, 两者只差测试执行期间的毫秒级流逝
        assert 0 <= expected - session.last_params["startTime"] < 5_000

    def test_um_hist_empty_window_returns_empty(self):
        df = run_async(OpenInterestFetcher(market="um").fetch(FakeSession([{}]), "BTCUSDT"))
        assert df.empty

    def test_cm_snapshot_maps_to_contract_columns(self):
        session = FakeSession([{"symbol": "BTCUSD_PERP", "openInterest": "123.45", "time": 1704067200000}])
        df = run_async(OpenInterestFetcher(market="cm").fetch(session, "BTCUSD_PERP"))
        assert session.last_url.endswith("/dapi/v1/openInterest")
        assert len(df) == 1
        # 列名对齐 DerivAdapter 契约: sumOpenInterest, timestamp(ms) 取交易所 time
        assert df.iloc[0]["sumOpenInterest"] == "123.45"
        assert df.iloc[0]["timestamp"] == 1704067200000
        assert "openInterest" not in df.columns

    def test_cm_snapshot_error_payload_returns_empty(self):
        # symbol 无效时接口返回错误对象, 应静默返回空并记录
        session = FakeSession([{"code": -1121, "msg": "Invalid symbol."}])
        df = run_async(OpenInterestFetcher(market="cm").fetch(session, "BOGUS"))
        assert df.empty


class TestDerivCollectorCollect:
    """collect() 编排层: 空数据必须抛错(诚实失败), 成功路径落盘 parquet"""

    @staticmethod
    def _patch_fetch(monkeypatch, df: pd.DataFrame):
        async def _fake_fetch(self, session, api_symbol, start_ms=None, end_ms=None, proxy=None):
            return df

        monkeypatch.setattr(FundingRateFetcher, "fetch", _fake_fetch)

    def test_collect_empty_result_raises(self, tmp_path, monkeypatch):
        # 不存在的 symbol 的 API 也返回 200+空数组, 空结果必须抛 RuntimeError
        # 让上层任务记为失败, 而不是静默跳过导致任务虚假显示"下载完成"
        self._patch_fetch(monkeypatch, pd.DataFrame())
        with pytest.raises(RuntimeError, match="数据源返回空"):
            DerivCollector(base_dir=str(tmp_path)).collect("fundingRate", "um", ["BOGUS"])

    def test_collect_success_saves_parquet(self, tmp_path, monkeypatch):
        df = pd.DataFrame({"symbol": ["BTCUSDT"], "timestamp": [1704067200000], "fundingRate": ["0.0001"]})
        self._patch_fetch(monkeypatch, df)
        DerivCollector(base_dir=str(tmp_path)).collect("fundingRate", "um", ["BTC/USDT"])
        files = list(tmp_path.rglob("*.parquet"))
        assert len(files) == 1
        # 落盘目录契约: {data_type}/{market}/{storage_symbol}/
        assert "BTCUSDT" in str(files[0].parent)


# =================== 符号规范化 ===================


class TestSymbolNormalization:
    def test_storage_symbol(self):
        assert to_storage_symbol("BTC/USDT") == "BTCUSDT"
        assert to_storage_symbol("btcusdt") == "BTCUSDT"
        assert to_storage_symbol("BTCUSDT") == "BTCUSDT"

    def test_api_symbol_um(self):
        assert to_api_symbol("um", "BTC/USDT") == "BTCUSDT"
        assert to_api_symbol("um", "BTCUSDC") == "BTCUSDC"

    def test_api_symbol_cm(self):
        assert to_api_symbol("cm", "BTC/USDT") == "BTCUSD_PERP"
        assert to_api_symbol("cm", "BTCUSD") == "BTCUSD_PERP"
        assert to_api_symbol("cm", "BTCUSD_PERP") == "BTCUSD_PERP"
        assert to_api_symbol("cm", "BTCUSDT_230929") == "BTCUSD_230929"


def run_async(coro):
    """同步运行一个 asyncio coroutine"""
    import asyncio

    return asyncio.run(coro)
