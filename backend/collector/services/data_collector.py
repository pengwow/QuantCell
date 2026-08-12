"""数据采集门面类

统一入口：根据 data_type 路由到 KlineCollector / ArchiveCollector / DerivCollector。
"""

import os
from pathlib import Path
from typing import List, Optional

from collector.schemas.data import (
    _ARCHIVE_TYPES,
    _DERIV_TYPES,
    _KLINE_TYPES,
)
from exchange.binance.downloader import BinanceDownloader
from exchange.binance.archive.factory import BinanceArchiveFactory
from utils import get_source_data_dir

_DEFAULT_DATA_DIR = str(get_source_data_dir())


# —— 工具函数 ——

def _candle_type_from_market(market: str) -> str:
    """将 market 映射为 downloader 所需的 candle_type"""
    return "spot" if market == "spot" else "futures"


def _market_type_from_str(market: str):
    """将字符串映射为 MarketType 枚举"""
    from exchange.binance.archive.kinds import MarketType
    return {"spot": MarketType.SPOT, "um": MarketType.FUTURES_UM, "cm": MarketType.FUTURES_CM}[market]


# —— K线采集器（封装现有 BinanceDownloader）——

class KlineCollector:
    """K线数据采集器，封装现有 BinanceDownloader 实现"""

    def __init__(self, base_dir: str = _DEFAULT_DATA_DIR):
        self.base_dir = Path(base_dir)

    def collect(
        self,
        data_type: str,
        market: str,
        symbols: List[str],
        intervals: List[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
        max_workers: int = 1,
        mode: str = "inc",
    ) -> None:
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
        symbols: List[str],
        intervals: Optional[List[str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> None:
        market_type = _market_type_from_str(market)
        interval = intervals[0] if intervals else None
        proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")

        downloader = self._factory.create(
            kind=data_type,
            market=market_type,
            base_dir=self.base_dir,
            symbol=symbols[0] if symbols else "",
            interval=interval,
            proxy=proxy,
        )
        downloader.collect_data(symbols=symbols, start=start or "2024-01-01", end=end or "2025-12-31")


# —— 统一入口 ——

class DataCollector:
    """数据采集门面类，根据 data_type 路由到对应的子采集器"""

    def __init__(self, base_dir: str = _DEFAULT_DATA_DIR):
        self.base_dir = base_dir

    def collect(
        self,
        data_type: str,
        market: str,
        symbols: List[str],
        intervals: Optional[List[str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
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
            )
        else:
            raise ValueError(f"未知的数据类型: {data_type}")
