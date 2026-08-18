"""数据适配器基类 — 定义统一的数据加载和转换接口。

所有适配器将不同数据源类型（aggTrades/bookDepth/fundingRate 等）
转换为 axon_quant 引擎可消费的 OHLCV DataFrame 格式。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from utils import get_source_data_dir
from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class LoadConfig:
    """数据加载配置。"""

    symbol: str
    data_type: str
    market: str = "spot"
    interval: str = "1h"
    start: str | None = None
    end: str | None = None


@dataclass
class AdapterResult:
    """适配器输出结果。"""

    data: pd.DataFrame
    features: pd.DataFrame | None = None
    metadata: dict = field(default_factory=dict)


class BaseDataAdapter(ABC):
    """数据适配器基类。

    子类必须覆盖 _SUPPORTED_TYPES 和 load() 方法。
    """

    _SUPPORTED_TYPES: set = set()

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = get_source_data_dir()
        self.base_dir = base_dir

    @abstractmethod
    def load(self, config: LoadConfig) -> AdapterResult:
        """加载并转换数据。"""
        ...

    def supports(self, data_type: str) -> bool:
        """是否支持该数据类型。"""
        return data_type in self._SUPPORTED_TYPES

    def _find_parquet(
        self,
        data_type: str,
        market: str,
        symbol: str,
        interval: str = "",
    ) -> Path | None:
        """查找 Parquet 文件。

        按多个模式顺序搜索，返回最新匹配的文件。
        """
        search_patterns = []
        if interval:
            search_patterns.append(
                self.base_dir / data_type / market / symbol / f"{symbol}-{data_type}-{interval}-*.parquet"
            )
        search_patterns.append(self.base_dir / data_type / market / symbol / f"{symbol}-{data_type}-*.parquet")
        search_patterns.append(self.base_dir / data_type / market / symbol / "*.parquet")

        for pattern in search_patterns:
            if pattern.parent.exists():
                matched = sorted(pattern.parent.glob(pattern.name))
                if matched:
                    return matched[-1]

        msg = f"未找到数据文件: type={data_type}, market={market}, symbol={symbol}, interval={interval}"
        raise FileNotFoundError(msg)

    def _load_parquet(self, path: Path) -> pd.DataFrame:
        """加载 Parquet 文件。"""
        from utils.parquet_utils import load_from_parquet

        logger.info(f"加载数据: {path}")
        return load_from_parquet(path)

    def _filter_by_date(
        self,
        df: pd.DataFrame,
        start: str | None,
        end: str | None,
    ) -> pd.DataFrame:
        """按日期筛选。"""
        if not start and not end:
            return df

        from utils.timestamp_utils import convert_to_datetime

        df = df.copy()
        if "timestamp" in df.columns:
            df["_datetime"] = convert_to_datetime(df["timestamp"])
        elif not isinstance(df.index, pd.DatetimeIndex):
            df["_datetime"] = convert_to_datetime(df.index)
        else:
            df["_datetime"] = df.index

        if start:
            df = df[df["_datetime"] >= pd.to_datetime(start)]
        if end:
            df = df[df["_datetime"] <= pd.to_datetime(end)]

        return df.drop(columns=["_datetime"], errors="ignore")

    def _generate_ns_timestamps(self, df: pd.DataFrame) -> pd.Series:
        """从索引或日期列生成纳秒时间戳。

        ponytail: 使用项目统一的 to_nanoseconds 函数
        """
        from utils.timestamp_utils import to_nanoseconds

        if isinstance(df.index, pd.DatetimeIndex):
            return pd.Series(
                [to_nanoseconds(ts.value) for ts in df.index],
                index=df.index,
            )
        elif "date" in df.columns:
            return df["date"].apply(to_nanoseconds)
        elif "timestamp" in df.columns:
            return df["timestamp"].apply(to_nanoseconds)
        else:
            # 使用行号生成伪时间戳
            return pd.Series(
                [int(i * 86400 * 1e9) for i in range(len(df))],
                index=df.index,
            )
