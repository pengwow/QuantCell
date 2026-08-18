"""OrderBookAdapter — 盘口数据适配器。

支持: bookDepth, bookTicker
提取 mid-price 和 spread 特征，聚合为 OHLCV。
"""

import pandas as pd

from utils.logger import LogType, get_logger

from .base_adapter import AdapterResult, BaseDataAdapter, LoadConfig

logger = get_logger(__name__, LogType.APPLICATION)


class OrderBookAdapter(BaseDataAdapter):
    """盘口数据适配器。

    提取 mid-price 和 spread 特征，聚合为 OHLCV bars。
    """

    _SUPPORTED_TYPES = {"bookDepth", "bookTicker"}

    def load(self, config: LoadConfig) -> AdapterResult:
        """加载盘口数据并转换。"""
        path = self._find_parquet(config.data_type, config.market, config.symbol)
        df = self._load_parquet(path)

        if config.data_type == "bookTicker":
            processed_df = self._process_book_ticker(df, config.interval)
        elif config.data_type == "bookDepth":
            processed_df = self._process_book_depth(df, config.interval)
        else:
            msg = f"不支持的盘口类型: {config.data_type}"
            raise ValueError(msg)

        return AdapterResult(
            data=processed_df,
            metadata={
                "data_type": config.data_type,
                "symbol": config.symbol,
                "interval": config.interval or "1m",
                "original_rows": len(df),
                "aggregated_rows": len(processed_df),
                "has_mid_price_feature": True,
            },
        )

    def _process_book_ticker(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """处理 bookTicker 数据。"""
        from utils.timestamp_utils import convert_to_datetime, to_nanoseconds

        bid_col = self._find_column(df, ["bidPrice", "bestBid"])
        ask_col = self._find_column(df, ["askPrice", "bestAsk"])
        time_col = self._find_column(df, ["timestamp", "T", "time"])

        df = df.copy()
        df["datetime"] = convert_to_datetime(df[time_col])
        df.set_index("datetime", inplace=True)

        df["mid_price"] = (df[bid_col] + df[ask_col]) / 2
        df["spread"] = df[ask_col] - df[bid_col]

        agg_interval = interval or "1m"
        result = pd.DataFrame(
            {
                "Open": df["mid_price"].resample(agg_interval).first(),
                "High": df["mid_price"].resample(agg_interval).max(),
                "Low": df["mid_price"].resample(agg_interval).min(),
                "Close": df["mid_price"].resample(agg_interval).last(),
                "Volume": df.get("bidQty", pd.Series(0, index=df.index)).resample(agg_interval).sum(),
                "feature_mid_price": df["mid_price"].resample(agg_interval).mean(),
                "feature_spread": df["spread"].resample(agg_interval).mean(),
            }
        )

        result = result.dropna(subset=["Close"])
        result["timestamp"] = result.index.map(lambda ts: to_nanoseconds(ts.value))
        result = result.reset_index(drop=True)

        logger.info(f"bookTicker 聚合: {len(df)} ticks → {len(result)} bars")

        return result

    def _process_book_depth(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """处理 bookDepth 数据。"""
        from utils.timestamp_utils import convert_to_datetime, to_nanoseconds

        time_col = self._find_column(df, ["timestamp", "T", "time"])

        df = df.copy()
        df["datetime"] = convert_to_datetime(df[time_col])
        df.set_index("datetime", inplace=True)

        bid_price_col = None
        ask_price_col = None
        for col in df.columns:
            col_lower = col.lower()
            if "bid" in col_lower and "price" in col_lower:
                bid_price_col = col
            elif "ask" in col_lower and "price" in col_lower:
                ask_price_col = col

        if bid_price_col is None or ask_price_col is None:
            logger.warning("无法从 bookDepth 提取最优买卖价")
            price_col = df.columns[0]
            df["mid_price"] = df[price_col]
        else:
            df["mid_price"] = (df[bid_price_col] + df[ask_price_col]) / 2

        agg_interval = interval or "1m"
        result = pd.DataFrame(
            {
                "Open": df["mid_price"].resample(agg_interval).first(),
                "High": df["mid_price"].resample(agg_interval).max(),
                "Low": df["mid_price"].resample(agg_interval).min(),
                "Close": df["mid_price"].resample(agg_interval).last(),
                "Volume": pd.Series(0, index=df.index).resample(agg_interval).sum(),
                "feature_mid_price": df["mid_price"].resample(agg_interval).mean(),
            }
        )

        result = result.dropna(subset=["Close"])
        result["timestamp"] = result.index.map(lambda ts: to_nanoseconds(ts.value))
        result = result.reset_index(drop=True)

        logger.info(f"bookDepth 聚合: {len(df)} ticks → {len(result)} bars")

        return result

    def _find_column(self, df: pd.DataFrame, candidates: list) -> str:
        """查找列。"""
        for col in candidates:
            if col in df.columns:
                return col
        msg = f"未找到列: {candidates}，可用列: {list(df.columns)}"
        raise ValueError(msg)
