"""DerivAdapter — 衍生数据适配器。

支持: fundingRate, openInterest
需要结合 markPriceKlines 作为基础价格数据。
"""

import pandas as pd

from utils.logger import LogType, get_logger

from .base_adapter import AdapterResult, BaseDataAdapter, LoadConfig

logger = get_logger(__name__, LogType.APPLICATION)


class DerivAdapter(BaseDataAdapter):
    """衍生数据适配器。

    加载 fundingRate/openInterest 数据，结合 markPriceKlines 作为
    基础价格数据，注入衍生特征列。
    """

    _SUPPORTED_TYPES = {"fundingRate", "openInterest"}

    def load(self, config: LoadConfig) -> AdapterResult:
        """加载衍生数据并转换。"""
        if config.data_type == "fundingRate":
            return self._process_funding_rate(config)
        elif config.data_type == "openInterest":
            return self._process_open_interest(config)
        else:
            msg = f"不支持的衍生数据类型: {config.data_type}"
            raise ValueError(msg)

    def _process_funding_rate(self, config: LoadConfig) -> AdapterResult:
        """处理资金费率数据。"""
        # 先检查 markPriceKlines 是否存在（基础价格数据源）
        mark_price_df = self._try_load_mark_price(config)

        if mark_price_df is None:
            msg = (
                "资金费率回测需要 markPriceKlines 作为基础价格数据。\n"
                "请先下载: python data.py download "
                f"-s {config.symbol} -t markPriceKlines --market {config.market}"
            )
            raise ValueError(msg)

        # 加载资金费率数据
        funding_path = self._find_parquet("fundingRate", config.market, config.symbol, config.interval)
        funding_df = self._load_parquet(funding_path)

        base_df = mark_price_df[["timestamp", "Open", "High", "Low", "Close", "Volume"]].copy()

        funding_feature = self._align_feature_to_dataframe(base_df, funding_df, "fundingRate")
        base_df["feature_funding_rate"] = funding_feature

        return AdapterResult(
            data=base_df,
            metadata={
                "data_type": "fundingRate",
                "source": "markPriceKlines + fundingRate",
                "has_funding_feature": True,
            },
        )

    def _process_open_interest(self, config: LoadConfig) -> AdapterResult:
        """处理持仓量数据。"""
        # 先检查 markPriceKlines 是否存在（基础价格数据源）
        mark_price_df = self._try_load_mark_price(config)

        if mark_price_df is None:
            msg = (
                "持仓量回测需要 markPriceKlines 作为基础价格数据。\n"
                "请先下载: python data.py download "
                f"-s {config.symbol} -t markPriceKlines --market {config.market}"
            )
            raise ValueError(msg)

        # 加载持仓量数据
        oi_path = self._find_parquet("openInterest", config.market, config.symbol, config.interval)
        oi_df = self._load_parquet(oi_path)

        base_df = mark_price_df[["timestamp", "Open", "High", "Low", "Close", "Volume"]].copy()

        base_df["feature_open_interest"] = self._align_feature_to_dataframe(base_df, oi_df, "sumOpenInterest")
        base_df["feature_open_interest_value"] = self._align_feature_to_dataframe(
            base_df, oi_df, "sumOpenInterestValue"
        )

        return AdapterResult(
            data=base_df,
            metadata={
                "data_type": "openInterest",
                "source": "markPriceKlines + openInterest",
                "has_oi_feature": True,
            },
        )

    def _try_load_mark_price(self, config: LoadConfig) -> pd.DataFrame | None:
        """尝试加载 markPriceKlines。"""
        try:
            path = self._find_parquet("markPriceKlines", config.market, config.symbol, config.interval)
            df = self._load_parquet(path)
            from .kline_adapter import KlineAdapter

            adapter = KlineAdapter()
            df = adapter._normalize_columns(df)
            if "timestamp" not in df.columns:
                df["timestamp"] = self._generate_ns_timestamps(df)
            return df
        except FileNotFoundError:
            return None

    def _align_feature_to_dataframe(
        self,
        base_df: pd.DataFrame,
        feature_df: pd.DataFrame,
        feature_col: str,
    ) -> pd.Series:
        """将特征数据对齐到基础数据的时间戳。"""
        from utils.timestamp_utils import convert_to_datetime

        feature_time_col = None
        for col in ["fundingTime", "timestamp", "T", "time"]:
            if col in feature_df.columns:
                feature_time_col = col
                break

        if feature_time_col is None:
            return pd.Series(0.0, index=base_df.index)

        feature_df = feature_df.copy()
        feature_df["_datetime"] = convert_to_datetime(feature_df[feature_time_col])
        feature_df = feature_df.set_index("_datetime")

        if feature_col not in feature_df.columns:
            logger.warning(f"特征列 {feature_col} 不存在")
            return pd.Series(0.0, index=base_df.index)

        base_datetimes = convert_to_datetime(base_df["timestamp"])
        feature = feature_df[feature_col]

        aligned = feature.reindex(base_datetimes, method="ffill")
        aligned = aligned.fillna(0.0)

        return aligned.values
