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
        proxy: str | None = None,
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
