from abc import ABC, abstractmethod
from typing import Optional, List, Dict
import pandas as pd
from pathlib import Path


class DataProvider(ABC):
    """数据提供者抽象基类

    定义数据提供者的统一接口，支持不同的数据源实现（Parquet文件、数据库等）。
    遵循依赖倒置原则，业务逻辑依赖此抽象接口而非具体实现。
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
        """
        获取K线数据

        Args:
            symbol: 交易对符号（如 BTCUSDT）
            interval: 时间周期（如 1m, 5m, 15m, 1h, 4h, 1d）
            candle_type: 市场类型 (spot/future)
            start: 开始时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
            end: 结束时间

        Returns:
            pd.DataFrame: 包含 timestamp, open, high, low, close, volume 的DataFrame

        Raises:
            FileNotFoundError: 当指定的数据不存在时
        """
        pass

    @abstractmethod
    def list_available_symbols(
        self,
        candle_type: str = "spot",
        interval: Optional[str] = None
    ) -> List[Dict]:
        """
        列出可用的交易对

        Args:
            candle_type: 市场类型 (spot/future)
            interval: 可选，筛选特定时间周期的交易对

        Returns:
            List[Dict]: [{symbol: str, intervals: List[str]}, ...]
                例如: [{"symbol": "BTCUSDT", "intervals": ["1m", "5m", "1h"]}]
        """
        pass

    @abstractmethod
    def get_available_intervals(
        self,
        symbol: str,
        candle_type: str = "spot"
    ) -> List[str]:
        """
        获取指定交易对的可用时间周期

        Args:
            symbol: 交易对符号（如 BTCUSDT）
            candle_type: 市场类型 (spot/future)

        Returns:
            List[str]: 如 ['1m', '5m', '15m', '1h', '4h', '1d']
        """
        pass
