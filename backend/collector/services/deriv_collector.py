"""衍生数据采集器

支持资金费率(fundingRate)和持仓量(openInterest)等衍生品数据的采集。
数据通过 Binance REST API 获取，存储为 Parquet 格式。
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import aiohttp
import pandas as pd

from collector.config import get_binance_proxy
from utils import get_source_data_dir
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

_DEFAULT_DATA_DIR = str(get_source_data_dir())

# 市场 → API 基地址映射
_API_BASE = {
    "um": "https://fapi.binance.com",
    "cm": "https://dapi.binance.com",
}


def _market_from_str(market: str) -> str:
    """将 market 字符串映射为 API 基地址 key"""
    return market


def to_storage_symbol(symbol: str) -> str:
    """本地符号 → 落盘符号(无斜杠大写)

    契约与回测侧 data_provider.normalize_symbol 一致:
    BTC/USDT → BTCUSDT。目录层级与文件名都必须用同一格式,
    否则 Path 拼接时斜杠会拆出伪层级导致加载侧找不到文件。
    """
    return symbol.upper().replace("/", "")


def to_api_symbol(market: str, symbol: str) -> str:
    """本地符号 → Binance REST API 符号

    - um 直接拼接: BTC/USDT → BTCUSDT
    - cm 是 USD 计价合约, 且接口要求带合约后缀: BTC/USDT → BTCUSD_PERP
      币本位的资金费率/持仓量只有永续(与当季)有值, 默认补 _PERP
    - 已是 API 格式的输入保持幂等
    """
    symbol = symbol.upper().replace("/", "")
    if market != "cm":
        return symbol
    # cm 一律 USD 计价: USDT 计价的输入(误选)统一换算, 含交割合约缩写 BTCUSDT_230929
    symbol = symbol.replace("USDT", "USD")
    if "_" not in symbol:
        symbol += "_PERP"
    return symbol


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
        start_time: int | None = None,
        end_time: int | None = None,
        proxy: str | None = None,
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
      USDT-M: GET /futures/data/openInterestHist —— 历史序列端点,
              period 枚举固定 (5m~1d), 回溯上限 30 天, 分页 limit<=500
      COIN-M: GET /dapi/v1/openInterest —— 仅当前快照;
              币安未提供币本位历史序列端点, 无法按时间段回补, 每次采集只落一行

    落盘列对齐回测 DerivAdapter 消费契约:
    sumOpenInterest / sumOpenInterestValue, timestamp 为毫秒(由交易所返回)
    """

    # 下载界面 interval → openInterestHist period 枚举
    # 1m/3m 与历史端点最小粒度 5m 不匹配, 近似用 5m
    _PERIOD_MAP = {
        "1m": "5m",
        "3m": "5m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "6h",
        "12h": "12h",
        "1d": "1d",
        "3d": "1d",
        "1w": "1d",
    }
    _PERIOD_MS = {
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "2h": 7_200_000,
        "4h": 14_400_000,
        "6h": 21_600_000,
        "12h": 43_200_000,
        "1d": 86_400_000,
    }

    MAX_LOOKBACK_MS = 30 * 86_400_000
    HIST_PAGE_LIMIT = 500

    def __init__(self, market: str = "um", interval: str = "1h"):
        self.market = market
        self.api_base = _API_BASE[market]
        self.period = self._PERIOD_MAP.get(interval, "1h")

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        proxy: str | None = None,
    ) -> pd.DataFrame:
        """um 走历史序列端点按时间段回补; cm 仅快照(忽略时间范围)"""
        if self.market == "um":
            return await self._fetch_hist(session, symbol, start_time, end_time, proxy)
        return await self._fetch_snapshot(session, symbol, proxy)

    async def _fetch_hist(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        start_ms: int | None,
        end_ms: int | None,
        proxy: str | None,
    ) -> pd.DataFrame:
        now_ms = int(datetime.now().timestamp() * 1000)
        earliest = now_ms - self.MAX_LOOKBACK_MS
        end_ms = min(end_ms, now_ms) if end_ms else now_ms
        if start_ms is None or start_ms < earliest:
            # 历史端点只保留最近 30 天, 更早的请求裁剪到上限
            start_ms = earliest
            logger.info(
                f"{symbol} openInterest: 起始时间超出历史端点 30 天回溯上限, "
                f"已裁剪至 {datetime.fromtimestamp(start_ms / 1000, UTC).isoformat()}"
            )
        if start_ms >= end_ms:
            return pd.DataFrame()

        step_ms = self._PERIOD_MS[self.period]
        params: dict = {
            "symbol": symbol,
            "period": self.period,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": self.HIST_PAGE_LIMIT,
        }
        rows = []
        while True:
            async with session.get(
                f"{self.api_base}/futures/data/openInterestHist", params=params, proxy=proxy
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

            if not data:
                break
            rows.extend(data)
            if len(data) < self.HIST_PAGE_LIMIT:
                break
            # 分页: 用最后一条 timestamp 推进 startTime
            last_ms = int(data[-1]["timestamp"])
            if last_ms + step_ms > end_ms:
                break
            params["startTime"] = last_ms + 1

        return pd.DataFrame(rows)

    async def _fetch_snapshot(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        proxy: str | None,
    ) -> pd.DataFrame:
        """COIN-M 快照: 每次采集落一行(openInterest), 无法回补历史"""
        async with session.get(f"{self.api_base}/dapi/v1/openInterest", params={"symbol": symbol}, proxy=proxy) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if not data.get("openInterest"):
            if "code" in data:
                logger.warning(f"{symbol} openInterest 快照接口返回错误: {data}")
            return pd.DataFrame()

        # 列名对齐 DerivAdapter 契约(接口原始字段为 openInterest);
        # 币本位快照无 openInterestValue, value 列由加载侧按缺失处理
        row = {
            "symbol": data.get("symbol", symbol),
            "sumOpenInterest": data["openInterest"],
            "timestamp": int(data.get("time") or datetime.now().timestamp() * 1000),
        }
        return pd.DataFrame([row])


class LeverageBracketCollector:
    """币安杠杆档位采集器（仅 USDT-M 永续）

    Binance API:
      USDT-M: GET /fapi/v1/leverageBracket?symbol=BTCUSDT（无需鉴权）

    ``brackets[]`` 字段名与引擎 Bracket 的映射：
      notionalFloor → notional_floor、notionalCap → notional_cap、
      maintMarginRatio → mmr、cum → cum、initialLeverage → max_leverage，
      强平费固定取 taker 费率 0.001（币安接口不返回该字段）。
    """

    # 强平手续费：币安档位接口不返回，统一按 taker 费率近似
    LIQUIDATION_FEE_RATE = 0.001

    def __init__(self, market: str = "um"):
        self.market = market
        self.api_base = _API_BASE[market]

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        proxy: str | None = None,
    ) -> list[dict]:
        """异步获取单个 symbol 的完整档位表（按 notional_floor 升序）"""
        url = f"{self.api_base}/fapi/v1/leverageBracket"
        async with session.get(url, params={"symbol": symbol}, proxy=proxy) as resp:
            resp.raise_for_status()
            payload = await resp.json()

        # 成功响应是 [{symbol, brackets: [...]}]；出错时是 {"code": ..., "msg": ...}
        item = payload[0] if isinstance(payload, list) and payload else {}
        brackets = [
            {
                "notional_floor": float(b.get("notionalFloor", 0.0)),
                "notional_cap": float(b["notionalCap"]) if b.get("notionalCap") is not None else None,
                "mmr": float(b.get("maintMarginRatio", 0.0)),
                "cum": float(b.get("cum", 0.0)),
                "liquidation_fee_rate": self.LIQUIDATION_FEE_RATE,
                "max_leverage": float(b.get("initialLeverage", 1.0)),
            }
            for b in item.get("brackets", [])
        ]
        brackets.sort(key=lambda b: b["notional_floor"])
        return brackets

    def save(self, symbol: str, brackets: list[dict]) -> bool:
        """档位落库（按 symbol + market 幂等覆盖），供回测三级回退的 DB 层使用"""
        if not brackets:
            logger.warning(f"{symbol} 档位为空，跳过落库")
            return False

        # 函数内导入：DB 依赖是可选链路，采集器在无 DB 的纯脚本场景也应可导入
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import LeverageBracket

        init_database_config()
        try:
            with SessionLocal() as session:
                row = session.query(LeverageBracket).filter_by(symbol=symbol.upper(), market=self.market).first()
                if row is None:
                    row = LeverageBracket(symbol=symbol.upper(), market=self.market)
                    session.add(row)
                row.brackets_json = json.dumps(brackets, ensure_ascii=False)
                row.collected_at = datetime.now(UTC)
                session.commit()
            logger.info(f"{symbol} 杠杆档位已落库（{len(brackets)} 档）")
            return True
        except Exception as e:
            logger.error(f"{symbol} 杠杆档位落库失败: {e}")
            return False


class DerivCollector:
    """衍生数据采集器，支持资金费率和持仓量数据"""

    def __init__(self, base_dir: str = _DEFAULT_DATA_DIR):
        self.base_dir = Path(base_dir)

    def _build_save_dir(self, data_type: str, market: str, symbol: str) -> Path:
        """构建存储目录: data/source/{data_type}/{market}/{symbol}/"""
        save_dir = self.base_dir.joinpath(data_type, market, symbol)
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _parse_time_range(self, start: str | None, end: str | None) -> tuple[int | None, int | None]:
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
        symbols: list[str],
        start: str | None = None,
        end: str | None = None,
        intervals: list[str] | None = None,
    ) -> None:
        """采集衍生数据

        intervals 仅 openInterest 使用: 历史端点按 period 粒度拉取, 取首个周期
        """
        import asyncio

        start_ms, end_ms = self._parse_time_range(start, end)
        # 代理三级兜底: system_config 显式配置 → 环境变量 → 直连。
        # 国内环境直连 Binance 常被 DNS 污染, 直连会 Connect call failed
        proxy = get_binance_proxy() or os.environ.get("https_proxy") or os.environ.get("http_proxy")
        if proxy is None:
            logger.warning("未配置 Binance 代理(system_config exchange.binance.proxy / 环境变量), 将直连尝试")
        interval = (intervals[0] if intervals else "1h") if data_type == "openInterest" else "1h"

        async def _collect_all():
            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for symbol in symbols:
                    # 落盘目录/文件名统一无斜杠格式(与回测加载契约一致);
                    # API 请求符号按市场规范化(cm 需 BTCUSD_PERP)
                    storage_symbol = to_storage_symbol(symbol)
                    api_symbol = to_api_symbol(market, symbol)
                    save_dir = self._build_save_dir(data_type, market, storage_symbol)

                    if data_type == "fundingRate":
                        fetcher = FundingRateFetcher(market=market)
                        df = await fetcher.fetch(session, api_symbol, start_ms, end_ms, proxy=proxy)
                    elif data_type == "openInterest":
                        fetcher = OpenInterestFetcher(market=market, interval=interval)
                        df = await fetcher.fetch(session, api_symbol, start_ms, end_ms, proxy=proxy)
                    else:
                        logger.warning(f"未知的衍生数据类型: {data_type}")
                        continue

                    if df.empty:
                        # 空结果必须暴露为失败(诚实失败): 不存在的 symbol / 错误市场
                        # 的 API 也返回 200+空数组, 静默跳过会让任务虚假显示"下载完成"
                        raise RuntimeError(f"{symbol} {data_type}({api_symbol}): 数据源返回空, 无数据可落盘")

                    # 保存为 Parquet
                    date_str = datetime.now().strftime("%Y%m%d")
                    output_path = save_dir / f"{storage_symbol}-{data_type}-{date_str}.parquet"
                    df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)
                    logger.info(f"已保存 {symbol} {data_type} 数据到 {output_path} ({len(df)} 行)")

        asyncio.run(_collect_all())
