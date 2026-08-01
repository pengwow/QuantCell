"""衍生数据采集器

支持资金费率(fundingRate)和持仓量(openInterest)等衍生品数据的采集。
数据通过 Binance REST API 获取，存储为 Parquet 格式。
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiohttp
import pandas as pd

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 市场 → API 基地址映射
_API_BASE = {
    "um": "https://fapi.binance.com",
    "cm": "https://dapi.binance.com",
}


def _market_from_str(market: str) -> str:
    """将 market 字符串映射为 API 基地址 key"""
    return market


class FundingRateFetcher:
    """资金费率获取器

    Binance API:
      USDT-M: GET /fapi/v1/fundingRate
      COIN-M: GET /dapi/v1/fundingRate
    """

    def __init__(self, market: str = "um"):
        self.market = market
        self.api_base = _API_BASE[market]

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        proxy: Optional[str] = None,
    ) -> pd.DataFrame:
        """异步获取单个 symbol 的资金费率历史"""
        params = {"symbol": symbol}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        url = f"{self.api_base}/fapi/v1/fundingRate"
        if self.market == "cm":
            url = f"{self.api_base}/dapi/v1/fundingRate"

        all_rows = []
        limit = 1000
        while True:
            params["limit"] = limit
            async with session.get(url, params=params, proxy=proxy) as resp:
                resp.raise_for_status()
                data = await resp.json()

            if not data:
                break

            all_rows.extend(data)
            if len(data) < limit:
                break

            # 分页：使用最后一条记录的 fundingTime 作为下一次的 startTime
            last_time = data[-1].get("fundingTime", 0)
            if not last_time:
                break
            params["startTime"] = last_time + 1

        if not all_rows:
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)
        if "fundingTime" in df.columns:
            df = df.rename(columns={"fundingTime": "timestamp"})
        return df


class OpenInterestFetcher:
    """持仓量获取器

    Binance API:
      USDT-M: GET /fapi/v1/openInterest
      COIN-M: GET /dapi/v1/openInterest
    """

    def __init__(self, market: str = "um"):
        self.market = market
        self.api_base = _API_BASE[market]

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        proxy: Optional[str] = None,
    ) -> pd.DataFrame:
        """异步获取单个 symbol 的当前持仓量"""
        url = f"{self.api_base}/fapi/v1/openInterest"
        if self.market == "cm":
            url = f"{self.api_base}/dapi/v1/openInterest"

        params = {"symbol": symbol}
        async with session.get(url, params=params, proxy=proxy) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if not data:
            return pd.DataFrame()

        # 添加当前时间戳
        data["timestamp"] = int(datetime.now().timestamp() * 1_000_000_000)
        return pd.DataFrame([data])


class DerivCollector:
    """衍生数据采集器，支持资金费率和持仓量数据"""

    def __init__(self, base_dir: str = "data/source"):
        self.base_dir = Path(base_dir)

    def _build_save_dir(self, data_type: str, market: str, symbol: str) -> Path:
        """构建存储目录: data/source/{data_type}/{market}/{symbol}/"""
        save_dir = self.base_dir.joinpath(data_type, market, symbol)
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _parse_time_range(
        self, start: Optional[str], end: Optional[str]
    ) -> tuple[Optional[int], Optional[int]]:
        """将 YYYY-MM-DD 格式时间转换为毫秒时间戳"""
        start_ms = None
        end_ms = None
        if start:
            start_ms = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)
        if end:
            end_ms = int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000)
        return start_ms, end_ms

    def collect(
        self,
        data_type: str,
        market: str,
        symbols: List[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> None:
        """采集衍生数据"""
        import asyncio

        start_ms, end_ms = self._parse_time_range(start, end)
        proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")

        async def _collect_all():
            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for symbol in symbols:
                    save_dir = self._build_save_dir(data_type, market, symbol)

                    if data_type == "fundingRate":
                        fetcher = FundingRateFetcher(market=market)
                        df = await fetcher.fetch(session, symbol, start_ms, end_ms, proxy=proxy)
                    elif data_type == "openInterest":
                        fetcher = OpenInterestFetcher(market=market)
                        df = await fetcher.fetch(session, symbol, proxy=proxy)
                    else:
                        logger.warning(f"未知的衍生数据类型: {data_type}")
                        continue

                    if df.empty:
                        logger.info(f"{symbol} {data_type}: 无数据")
                        continue

                    # 保存为 Parquet
                    date_str = datetime.now().strftime("%Y%m%d")
                    output_path = save_dir / f"{symbol}-{data_type}-{date_str}.parquet"
                    df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
                    logger.info(f"已保存 {symbol} {data_type} 数据到 {output_path} ({len(df)} 行)")

        asyncio.run(_collect_all())
