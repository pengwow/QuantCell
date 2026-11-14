"""市场数据补充服务：现货订单簿快照 + 永续 OI/资金费率历史。

低频图表兜底用途，不复用全局 client 连接池；直连 binance 公有接口（无需鉴权）。
ponytail: 每请求新建 aiohttp.ClientSession 的天花板是连接握手开销（~几十 ms），
对图表初始兜底无感；升级路径是复用 collector 的 session 池/连接复用。

Fetcher 复用 collector/services/deriv_collector.py 的实现：
- FundingRateFetcher(market='um').fetch(session, symbol, start_ms, end_ms)
  → DataFrame{timestamp, fundingRate}（固定 8h 结算，fundingRate 为字符串需转 float）
- OpenInterestFetcher(market='um', interval=...).fetch(...)
  → DataFrame{timestamp, sumOpenInterest, sumOpenInterestValue}
  （interval ∈ {5m,15m,30m,1h,2h,4h,6h,12h,1d}，历史接口仅保留近 30 天）
"""

import time
from typing import Any

import aiohttp

from collector.services.deriv_collector import FundingRateFetcher, OpenInterestFetcher

SPOT_DEPTH_URL = "https://api.binance.com/api/v3/depth"
_30D_MS = 30 * 24 * 3600 * 1000  # OI 历史接口的上限窗口


async def fetch_depth_snapshot(symbol: str, limit: int) -> dict[str, Any]:
    """现货订单簿快照；symbol 形如 BTCUSDT。"""
    clean = symbol.replace("/", "").replace(":", "").upper()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            SPOT_DEPTH_URL,
            params={"symbol": clean, "limit": limit},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json()
    # depth 接口不带时间戳，用接受时刻兜底（毫秒，与前端 kline.t 对齐）
    return {
        "symbol": clean,
        "bids": [[float(p), float(q)] for p, q in payload.get("bids", [])],
        "asks": [[float(p), float(q)] for p, q in payload.get("asks", [])],
        "timestamp": int(time.time() * 1000),
    }


async def fetch_oi_history(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    """UM 永续未平仓合约历史；不支持品种/接口异常时抛原始异常由路由转 502。
    openInterest 统一取 USD 口径（sumOpenInterestValue）。"""
    fetcher = OpenInterestFetcher(market="um", interval=interval)
    end_ms = int(time.time() * 1000)
    async with aiohttp.ClientSession() as session:
        df = await fetcher.fetch(session, symbol.replace("/", "").upper(), end_ms - _30D_MS, end_ms)
    rows: list[dict[str, Any]] = []
    for _, row in df.tail(limit).iterrows():
        rows.append(
            {
                "timestamp": int(row["timestamp"]),
                "openInterest": float(row["sumOpenInterestValue"]),
                "openInterestValue": float(row["sumOpenInterestValue"]),
            }
        )
    return rows


async def fetch_funding_history(symbol: str, limit: int) -> list[dict[str, Any]]:
    """UM 永续资金费率历史（8h 固定结算，无 interval 维度）。"""
    fetcher = FundingRateFetcher(market="um")
    end_ms = int(time.time() * 1000)
    async with aiohttp.ClientSession() as session:
        df = await fetcher.fetch(
            session,
            symbol.replace("/", "").upper(),
            end_ms - 14 * 24 * 3600 * 1000,
            end_ms,  # 8h * 42 = 14 天足够覆盖 limit≤42
        )
    return [
        {"timestamp": int(row["timestamp"]), "fundingRate": float(row["fundingRate"])}
        for _, row in df.tail(limit).iterrows()
    ]
