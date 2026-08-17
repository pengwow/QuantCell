"""TickAdapter — Tick 级数据适配器。

支持: aggTrades, trades
将逐笔成交数据按时间窗口聚合为 OHLCV bar。
"""

from typing import Optional

import pandas as pd
import numpy as np

from utils.logger import get_logger, LogType
from .base_adapter import AdapterResult, BaseDataAdapter, LoadConfig

logger = get_logger(__name__, LogType.APPLICATION)


class TickAdapter(BaseDataAdapter):
    """Tick 级数据适配器。

    将逐笔成交数据按时间窗口聚合为 OHLCV。
    """

    _SUPPORTED_TYPES = {"aggTrades", "trades"}

    DEFAULT_INTERVALS = {
        "aggTrades": "5m",
        "trades": "5m",
    }

    _TIME_COLUMNS = ["timestamp", "trade_time", "T", "time"]
    _PRICE_COLUMNS = ["price", "p", "executed_price"]
    _QTY_COLUMNS = ["quantity", "qty", "q", "volume"]

    def load(self, config: LoadConfig) -> AdapterResult:
        """加载 Tick 数据并聚合为 OHLCV。"""
        interval = config.interval or self.DEFAULT_INTERVALS.get(
            config.data_type, "5m"
        )

        path = self._find_parquet(config.data_type, config.market, config.symbol)
        df = self._load_parquet(path)

        time_col = self._detect_column(df, self._TIME_COLUMNS, "时间")
        price_col = self._detect_column(df, self._PRICE_COLUMNS, "价格")
        qty_col = self._detect_column(df, self._QTY_COLUMNS, "数量")

        ohlcv = self._aggregate_to_ohlcv(df, time_col, price_col, qty_col, interval)

        return AdapterResult(
            data=ohlcv,
            metadata={
                "data_type": config.data_type,
                "symbol": config.symbol,
                "interval": interval,
                "original_rows": len(df),
                "aggregated_rows": len(ohlcv),
            },
        )

    def _detect_column(
        self, df: pd.DataFrame, candidates: list, col_type: str
    ) -> str:
        """检测列名。"""
        for col in candidates:
            if col in df.columns:
                return col
        raise ValueError(f"未找到{col_type}列，可用列: {list(df.columns)}")

    def _aggregate_to_ohlcv(
        self,
        df: pd.DataFrame,
        time_col: str,
        price_col: str,
        qty_col: str,
        interval: str,
    ) -> pd.DataFrame:
        """聚合 Tick 数据为 OHLCV。"""
        from utils.timestamp_utils import convert_to_datetime, to_nanoseconds

        df = df.copy()
        df["datetime"] = convert_to_datetime(df[time_col])
        df.set_index("datetime", inplace=True)

        resampled = pd.DataFrame()
        resampled["Open"] = df[price_col].resample(interval).first()
        resampled["High"] = df[price_col].resample(interval).max()
        resampled["Low"] = df[price_col].resample(interval).min()
        resampled["Close"] = df[price_col].resample(interval).last()
        resampled["Volume"] = df[qty_col].resample(interval).sum()

        resampled = resampled.dropna(subset=["Close"])

        resampled["timestamp"] = resampled.index.map(
            lambda ts: to_nanoseconds(ts.value)
        )

        result = resampled.reset_index(drop=True)

        logger.info(
            f"Tick 聚合: {len(df)} ticks → {len(result)} bars (interval={interval})"
        )

        return result
