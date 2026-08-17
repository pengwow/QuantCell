"""KlineAdapter — K线类数据适配器。

支持: kline, markPriceKlines, indexPriceKlines, premiumIndexKlines
直接加载 OHLCV 数据，无需转换。
"""

from typing import Optional

import pandas as pd

from .base_adapter import AdapterResult, BaseDataAdapter, LoadConfig


class KlineAdapter(BaseDataAdapter):
    """K线类数据适配器。

    直接加载 OHLCV 数据，标准化列名为 Open/High/Low/Close/Volume。
    """

    _SUPPORTED_TYPES = {"kline", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"}

    _COLUMN_MAPPING = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }

    def load(self, config: LoadConfig) -> AdapterResult:
        """加载 K 线数据。"""
        path = self._find_parquet(
            config.data_type, config.market, config.symbol, config.interval
        )
        df = self._load_parquet(path)

        df = self._normalize_columns(df)

        if config.start or config.end:
            df = self._filter_by_date(df, config.start, config.end)

        if "timestamp" not in df.columns:
            df["timestamp"] = self._generate_ns_timestamps(df)

        return AdapterResult(
            data=df,
            metadata={
                "data_type": config.data_type,
                "symbol": config.symbol,
                "interval": config.interval,
                "rows": len(df),
            },
        )

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化列名为大写 OHLCV。"""
        df = df.copy()
        for src, dst in self._COLUMN_MAPPING.items():
            for variant in [src, src.upper(), src.capitalize()]:
                if variant in df.columns and dst not in df.columns:
                    df[dst] = df[variant]
                    break
        return df
