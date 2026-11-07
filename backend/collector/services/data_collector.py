"""数据采集门面类

统一入口：根据 data_type 路由到 KlineCollector / ArchiveCollector / DerivCollector。
"""

import os
from pathlib import Path

from collector.config import get_binance_proxy
from collector.schemas.data import (
    _ARCHIVE_TYPES,
    _DERIV_TYPES,
    _KLINE_TYPES,
)
from exchange.binance.archive.factory import BinanceArchiveFactory
from exchange.binance.downloader import BinanceDownloader
from utils import get_source_data_dir

_DEFAULT_DATA_DIR = str(get_source_data_dir())


# —— 工具函数 ——


def _candle_type_from_market(market: str) -> str:
    """将 market 映射为 downloader 所需的 candle_type"""
    return "spot" if market == "spot" else "futures"


def _market_type_from_str(market: str):
    """将字符串映射为 MarketType 枚举"""
    from exchange.binance.archive.kinds import MarketType

    return {
        "spot": MarketType.SPOT,
        "um": MarketType.FUTURES_UM,
        "cm": MarketType.FUTURES_CM,
    }[market]


# —— K线采集器（封装现有 BinanceDownloader）——


class KlineCollector:
    """K线数据采集器，封装现有 BinanceDownloader 实现"""

    def __init__(self, base_dir: str = _DEFAULT_DATA_DIR):
        self.base_dir = Path(base_dir)

    def collect(
        self,
        data_type: str,
        market: str,
        symbols: list[str],
        intervals: list[str],
        start: str | None = None,
        end: str | None = None,
        max_workers: int = 1,
        mode: str = "inc",
    ) -> None:
        # 代理兜底与 DerivCollector 同口径: system_config → 环境变量 → 直连。
        # 注入环境变量后, BinanceDownloader 的 aiohttp(trust_env=True)
        # 与 requests(默认 trust_env) 都会从环境变量读取
        proxy = get_binance_proxy() or os.environ.get("https_proxy") or os.environ.get("http_proxy")
        if proxy:
            os.environ.setdefault("https_proxy", proxy)
            os.environ.setdefault("http_proxy", proxy)
        candle_type = _candle_type_from_market(market)
        for interval in intervals:
            for symbol in symbols:
                downloader = BinanceDownloader(
                    save_dir=str(self.base_dir.joinpath(data_type, market, symbol, interval)),
                    candle_type=candle_type,
                    start=start,
                    end=end,
                    interval=interval,
                    max_workers=max_workers,
                    symbols=[symbol],
                    mode=mode,
                )
                downloader.collect_data()


# —— 归档数据采集器（桥接 BinanceArchiveFactory）——


class ArchiveCollector:
    """归档数据采集器，封装 BinanceArchiveFactory"""

    def __init__(self, base_dir: str = _DEFAULT_DATA_DIR):
        self.base_dir = base_dir
        self._factory = BinanceArchiveFactory()

    def collect(
        self,
        data_type: str,
        market: str,
        symbols: list[str],
        intervals: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        market_type = _market_type_from_str(market)
        interval = intervals[0] if intervals else None
        # 代理兜底与 DerivCollector 同口径: system_config → 环境变量 → 直连
        proxy = get_binance_proxy() or os.environ.get("https_proxy") or os.environ.get("http_proxy")

        # 归档 URL 与落盘目录需要 API 符号: LTC/USDT → LTCUSDT(LTCUSD_PERP/cm),
        # 带斜杠的原始符号会拼出坏 URL 且 Path 拆出伪层级
        from collector.services.deriv_collector import to_api_symbol

        api_symbol = to_api_symbol(market, symbols[0]) if symbols else ""

        downloader = self._factory.create(
            kind=data_type,
            market=market_type,
            base_dir=self.base_dir,
            symbol=api_symbol,
            interval=interval,
            proxy=proxy,
        )
        downloader.collect_data(
            symbols=[api_symbol] if api_symbol else [], start=start or "2024-01-01", end=end or "2025-12-31"
        )


# —— 统一入口 ——


class DataCollector:
    """数据采集门面类，根据 data_type 路由到对应的子采集器"""

    def __init__(self, base_dir: str = _DEFAULT_DATA_DIR):
        self.base_dir = base_dir

    def collect(
        self,
        data_type: str,
        market: str,
        symbols: list[str],
        intervals: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        max_workers: int = 1,
        mode: str = "inc",
    ) -> None:
        if data_type in _KLINE_TYPES:
            collector = KlineCollector(self.base_dir)
            collector.collect(
                data_type=data_type,
                market=market,
                symbols=symbols,
                intervals=intervals or ["1h"],
                start=start,
                end=end,
                max_workers=max_workers,
                mode=mode,
            )
        elif data_type in _ARCHIVE_TYPES:
            collector = ArchiveCollector(self.base_dir)
            collector.collect(
                data_type=data_type,
                market=market,
                symbols=symbols,
                intervals=intervals,
                start=start,
                end=end,
            )
        elif data_type in _DERIV_TYPES:
            from collector.services.deriv_collector import DerivCollector

            collector = DerivCollector(self.base_dir)
            collector.collect(
                data_type=data_type,
                market=market,
                symbols=symbols,
                start=start,
                end=end,
                intervals=intervals,
            )
        else:
            msg = f"未知的数据类型: {data_type}"
            raise ValueError(msg)
