from abc import ABC, abstractmethod
from typing import Optional, Dict
import pandas as pd


class DataProvider(ABC):
    """数据提供者抽象接口

    定义数据提供者的统一接口，支持从不同数据源（Parquet文件、数据库等）读取K线数据。
    子类需要实现 get_kline_data 方法。
    """

    @abstractmethod
    def get_kline_data(
        self,
        symbol: str,
        interval: str,
        candle_type: str = "spot",
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """获取K线数据

        Args:
            symbol: 交易对（如 BTCUSDT）
            interval: K线周期（如 15m, 1h, 4h）
            candle_type: 市场类型 ("spot" 或 "future")
            start: 开始时间（ISO格式字符串，如 "2024-01-01T00:00:00Z"）
            end: 结束时间（ISO格式字符串）

        Returns:
            K线数据 DataFrame，包含 open, high, low, close, volume 等列
        """
        pass

    @abstractmethod
    def list_symbols(self, candle_type: str = "spot") -> list:
        """列出可用的交易对

        Args:
            candle_type: 市场类型 ("spot" 或 "future")

        Returns:
            交易对列表
        """
        pass

    @abstractmethod
    def list_intervals(self, symbol: str, candle_type: str = "spot") -> list:
        """列出指定交易对可用的K线周期

        Args:
            symbol: 交易对
            candle_type: 市场类型 ("spot" 或 "future")

        Returns:
            K线周期列表
        """
        pass
