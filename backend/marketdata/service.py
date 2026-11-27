"""
市场数据补充服务：现货订单簿快照 + 永续 OI/资金费率历史。

低频图表兜底用途，不复用全局 client 连接池；请求 binance 公有接口（无需鉴权）。
ponytail: 每请求新建 aiohttp.ClientSession 的天花板是连接握手开销（~几十 ms），
对图表初始兜底无感；升级路径是复用 collector 的 session 池/连接复用。

网络可用性：binance REST 域名在国内直连不可达（2026-11-14 实测超时，仅 WS 引擎
经代理可达），因此所有外发请求统一走 resolve_proxy()，与 collector 调用方的
代理解析顺序保持一致（系统配置 > .env PROXY_URL > shell 环境变量）。

Fetcher 复用 collector/services/deriv_collector.py 的实现：
- FundingRateFetcher(market='um').fetch(session, symbol, start_ms, end_ms)
  → DataFrame{timestamp, fundingRate}（固定 8h 结算，fundingRate 为字符串需转 float）
- OpenInterestFetcher(market='um', interval=...).fetch(...)
  → DataFrame{timestamp, sumOpenInterest, sumOpenInterestValue}
  （interval ∈ {5m,15m,30m,1h,2h,4h,6h,12h,1d}，历史接口仅保留近 30 天）
"""

import time
from datetime import UTC, datetime, timezone
from typing import Any

import aiohttp

from collector.services.deriv_collector import FundingRateFetcher, OpenInterestFetcher
from utils.proxy import resolve_proxy

SPOT_DEPTH_URL = "https://api.binance.com/api/v3/depth"
_30D_MS = 30 * 24 * 3600 * 1000  # OI 历史接口的上限窗口


async def fetch_depth_snapshot(symbol: str, limit: int) -> dict[str, Any]:
    """现货订单簿快照；symbol 形如 BTCUSDT。"""
    clean = symbol.replace("/", "").replace(":", "").upper()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            SPOT_DEPTH_URL,
            params={"symbol": clean, "limit": limit},
            proxy=resolve_proxy(),
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
        df = await fetcher.fetch(
            session, symbol.replace("/", "").upper(), end_ms - _30D_MS, end_ms, proxy=resolve_proxy()
        )
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
            proxy=resolve_proxy(),
        )
    return [
        {"timestamp": int(row["timestamp"]), "fundingRate": float(row["fundingRate"])}
        for _, row in df.tail(limit).iterrows()
    ]


# ---------------------------------------------------------------------------
# 实时最新价（价格计划参考价自动预览）
# ---------------------------------------------------------------------------

# Binance 公共 ticker：spot/margin 走现货 API，futures 走 U 本位合约 API，均无需鉴权
SPOT_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
FUTURES_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/price"

# 市场类型 → endpoint 映射；margin 保证金交易行情与现货一致，直接复用现货 ticker
_TICKER_URLS: dict[str, str] = {
    "spot": SPOT_TICKER_URL,
    "margin": SPOT_TICKER_URL,
    "futures": FUTURES_TICKER_URL,
}

# K线端点映射：margin 复用现货 K 线（与 ticker 同理），futures 走 U 本位合约 API
SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
_KLINES_URLS: dict[str, str] = {
    "spot": SPOT_KLINES_URL,
    "margin": SPOT_KLINES_URL,
    "futures": FUTURES_KLINES_URL,
}
_KLINES_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")
_KLINES_DEFAULT_LIMIT = 120
_KLINES_MAX_LIMIT = 500

# 30s 微缓存：只缓存成功结果，失败不缓存（重试继续打交易所如实暴露问题）。
# ponytail: 进程内 dict 无淘汰——调用方是人工打开弹窗时的预览，key 组合
# （exchange|symbol|market_type）有限不会膨胀；将来若变高频再换 LRU。
_PRICE_CACHE: dict[str, tuple[float, dict]] = {}
_PRICE_CACHE_TTL_SECONDS = 30.0


class UnsupportedExchangeError(ValueError):
    """请求的交易所/市场类型不在实时行情支持范围内（路由层转 400）"""


async def fetch_latest_price(
    symbol: str,
    market_type: str = "spot",
    exchange: str = "binance",
) -> dict:
    """回源交易所公共 ticker 取实时最新价。

    仅实时数据，不做本地 DB 降级：策略要在交易所真实使用，交易所不可达本身就
    是要暴露的问题；取价失败向上抛原始异常，由路由层转 502。
    """
    if exchange != "binance":
        raise UnsupportedExchangeError(f"暂不支持交易所 {exchange} 的实时行情")
    url = _TICKER_URLS.get(market_type)
    if url is None:
        raise UnsupportedExchangeError(f"暂不支持市场类型 {market_type} 的实时行情")

    clean_symbol = symbol.replace("/", "").replace(":", "").upper()
    cache_key = f"{exchange}|{clean_symbol}|{market_type}"
    now = time.monotonic()
    cached = _PRICE_CACHE.get(cache_key)
    if cached and cached[0] > now:
        return dict(cached[1])

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            params={"symbol": clean_symbol},
            proxy=resolve_proxy(),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json()

    result = {
        "symbol": clean_symbol,
        "price": float(payload["price"]),
        # 项目时间戳规范要求纳秒精度；stdlib isoformat 只支持到微秒（6 位），
        # 在小数段尾部补零 3 位凑足 9 位纳秒（等价于无人为精度损失）
        "ts": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "000+00:00"),
    }
    _PRICE_CACHE[cache_key] = (now + _PRICE_CACHE_TTL_SECONDS, result)
    return dict(result)


async def fetch_recent_klines(
    symbol: str,
    market_type: str = "spot",
    exchange: str = "binance",
    interval: str = "15m",
    limit: int | None = None,
) -> list[dict]:
    """回源币安公共 REST 拉最近 K 线序列（价格计划真实K线预览用，spec §1）。

    与 fetch_latest_price 同构但不写缓存：K 线是历史序列且预览随档位/周期切换
    重拉，缓存意义有限（ponytail 决策，升级路径是同款 30s 微缓存）。
    limit 缺省 120、clamp 1-500；interval 白名单 _KLINES_INTERVALS，
    越界 ValueError 由路由层转 422。失败上抛原始异常由路由层转 502。
    """
    if exchange != "binance":
        raise UnsupportedExchangeError(f"暂不支持交易所 {exchange} 的K线行情")
    url = _KLINES_URLS.get(market_type)
    if url is None:
        raise UnsupportedExchangeError(f"暂不支持市场类型 {market_type} 的K线行情")
    if interval not in _KLINES_INTERVALS:
        raise ValueError(f"不支持的K线周期: {interval}")
    lim = _KLINES_DEFAULT_LIMIT if limit is None else max(1, min(_KLINES_MAX_LIMIT, int(limit)))

    clean_symbol = symbol.replace("/", "").replace(":", "").upper()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            params={"symbol": clean_symbol, "interval": interval, "limit": lim},
            proxy=resolve_proxy(),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            payload = await resp.json()

    # binance 原生行 [open_time, open, high, low, close, volume, ...]，已按时间升序
    return [
        {
            "ts": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in payload
    ]
