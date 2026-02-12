"""
数据加载模块

支持从CSV/Parquet文件或数据库加载历史交易数据。
"""

import asyncio
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
import pandas as pd
from loguru import logger

from .models import KlineData, DataType
from .config import DataConfig


class DataSource(ABC):
    """数据源抽象基类"""
    
    @abstractmethod
    async def load_data(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[KlineData]:
        """加载数据"""
        pass
    
    @abstractmethod
    async def validate(self) -> bool:
        """验证数据源可用性"""
        pass


class FileDataSource(DataSource):
    """文件数据源"""
    
    def __init__(self, base_path: Union[str, Path]):
        self.base_path = Path(base_path)
        self._cache: Dict[str, pd.DataFrame] = {}
        self._is_single_file = False
        
        # 判断是单文件还是目录
        if self.base_path.exists() and self.base_path.is_file():
            self._is_single_file = True
    
    async def validate(self) -> bool:
        """验证数据源可用性"""
        if not self.base_path.exists():
            logger.error(f"Data path does not exist: {self.base_path}")
            return False
        
        # 支持文件或目录
        if self.base_path.is_file():
            logger.info(f"Using single data file: {self.base_path}")
            return True
        elif self.base_path.is_dir():
            logger.info(f"Using data directory: {self.base_path}")
            return True
        else:
            logger.error(f"Data path is neither a file nor a directory: {self.base_path}")
            return False
    
    def _get_file_path(self, symbol: str, interval: str) -> Path:
        """获取数据文件路径"""
        # 如果是单文件模式，直接返回该文件
        if self._is_single_file:
            return self.base_path
        
        # 尝试多种命名格式
        possible_names = [
            f"{symbol}_{interval}.csv",
            f"{symbol}_{interval}.parquet",
            f"{symbol}-{interval}.csv",
            f"{symbol}-{interval}.parquet",
            f"{symbol}.csv",
            f"{symbol}.parquet",
        ]
        
        for name in possible_names:
            path = self.base_path / name
            if path.exists():
                return path
        
        # 默认返回CSV格式
        return self.base_path / f"{symbol}_{interval}.csv"
    
    async def load_data(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[KlineData]:
        """从文件加载K线数据"""
        file_path = self._get_file_path(symbol, interval)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Data file not found: {file_path}")
        
        # 检查缓存
        cache_key = f"{symbol}_{interval}"
        if cache_key in self._cache:
            df = self._cache[cache_key]
        else:
            # 异步读取文件
            df = await self._read_file(file_path)
            self._cache[cache_key] = df
        
        # 时间过滤
        if start_time:
            df = df[df["timestamp"] >= start_time]
        if end_time:
            df = df[df["timestamp"] <= end_time]
        
        # 转换为KlineData列表
        klines = self._df_to_klines(df, symbol, interval)
        
        logger.info(f"Loaded {len(klines)} klines for {symbol} {interval} from {file_path}")
        return klines
    
    async def _read_file(self, file_path: Path) -> pd.DataFrame:
        """异步读取文件"""
        loop = asyncio.get_event_loop()
        
        if file_path.suffix == ".parquet":
            df = await loop.run_in_executor(None, pd.read_parquet, file_path)
        else:
            df = await loop.run_in_executor(None, pd.read_csv, file_path)
        
        # 标准化列名
        df = self._normalize_columns(df)
        
        return df
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化列名"""
        # 列名映射
        column_mapping = {
            # 时间列
            "datetime": "timestamp",
            "date": "timestamp",
            "time": "timestamp",
            "open_time": "timestamp",
            # 价格列
            "o": "open",
            "Open": "open",
            "h": "high",
            "High": "high",
            "l": "low",
            "Low": "low",
            "c": "close",
            "Close": "close",
            # 成交量列
            "v": "volume",
            "Volume": "volume",
            "vol": "volume",
            "quote_volume": "volume",
        }
        
        # 重命名列
        df = df.rename(columns=column_mapping)
        
        # 确保timestamp列是datetime类型
        if "timestamp" in df.columns:
            dtype = df["timestamp"].dtype
            if dtype == "object":
                # 字符串类型，转换为datetime
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            elif dtype in ["int64", "int32", "float64", "float32"]:
                # 整数或浮点数，可能是Unix时间戳（毫秒或秒）
                sample_val = df["timestamp"].iloc[0] if len(df) > 0 else 0
                if sample_val > 1e12:  # 毫秒时间戳
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                elif sample_val > 1e9:  # 秒时间戳
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                else:
                    # 尝试自动解析
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        return df
    
    def _df_to_klines(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
    ) -> List[KlineData]:
        """DataFrame转换为KlineData列表"""
        klines = []
        
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        for _, row in df.iterrows():
            try:
                # 确保 timestamp 是 datetime 类型
                ts = row["timestamp"]
                if isinstance(ts, (int, float)):
                    # Unix时间戳处理
                    if ts > 1e12:  # 毫秒
                        ts = datetime.fromtimestamp(ts / 1000)
                    else:  # 秒
                        ts = datetime.fromtimestamp(ts)
                elif not isinstance(ts, datetime):
                    ts = pd.to_datetime(ts).to_pydatetime()
                
                kline = KlineData(
                    symbol=symbol,
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    interval=interval,
                )
                klines.append(kline)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse row: {row.to_dict()}, error: {e}")
                continue
        
        return klines
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()


class DatabaseDataSource(DataSource):
    """数据库数据源"""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._conn: Optional[sqlite3.Connection] = None
    
    async def validate(self) -> bool:
        """验证数据源可用性"""
        try:
            conn = sqlite3.connect(self.connection_string)
            conn.close()
            return True
        except Exception:
            return False
    
    async def load_data(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[KlineData]:
        """从数据库加载K线数据"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._load_data_sync, symbol, interval, start_time, end_time
        )
    
    def _load_data_sync(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[KlineData]:
        """同步加载数据"""
        conn = sqlite3.connect(self.connection_string)
        
        # 构建查询
        table_name = f"kline_{interval}"
        query = f"""
            SELECT timestamp, open, high, low, close, volume
            FROM {table_name}
            WHERE symbol = ?
        """
        params = [symbol]
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp ASC"
        
        try:
            df = pd.read_sql_query(query, conn, params=params)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            
            klines = []
            for _, row in df.iterrows():
                kline = KlineData(
                    symbol=symbol,
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    interval=interval,
                )
                klines.append(kline)
            
            logger.info(f"Loaded {len(klines)} klines for {symbol} {interval} from database")
            return klines
            
        finally:
            conn.close()


class DataLoader:
    """数据加载器"""
    
    def __init__(self, config: DataConfig):
        self.config = config
        self._source: Optional[DataSource] = None
        self._loaded_data: Dict[str, List[KlineData]] = {}
    
    async def initialize(self):
        """初始化数据源"""
        if self.config.source_type == "file":
            if not self.config.file_path:
                raise ValueError("file_path is required for file source")
            self._source = FileDataSource(self.config.file_path)
        elif self.config.source_type == "database":
            if not self.config.db_connection:
                raise ValueError("db_connection is required for database source")
            self._source = DatabaseDataSource(self.config.db_connection)
        else:
            raise ValueError(f"Unsupported source type: {self.config.source_type}")
        
        # 验证数据源
        if not await self._source.validate():
            raise RuntimeError(
                f"Failed to validate data source. "
                f"Type: {self.config.source_type}, "
                f"Path: {self.config.file_path or self.config.db_connection}"
            )
        
        logger.info(f"Data loader initialized with {self.config.source_type} source")
    
    async def load_all_data(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, List[KlineData]]:
        """加载所有配置的数据"""
        if not self._source:
            raise RuntimeError("Data loader not initialized")
        
        result = {}
        
        for symbol in self.config.symbols:
            for interval in self.config.intervals:
                key = f"{symbol}_{interval}"
                
                try:
                    data = await self._source.load_data(
                        symbol=symbol,
                        interval=interval,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    result[key] = data
                    self._loaded_data[key] = data
                except Exception as e:
                    logger.error(f"Failed to load data for {key}: {e}")
                    continue
        
        return result
    
    async def load_symbol_data(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[KlineData]:
        """加载指定交易对的数据"""
        if not self._source:
            raise RuntimeError("Data loader not initialized")
        
        key = f"{symbol}_{interval}"
        
        # 检查缓存
        if key in self._loaded_data:
            return self._loaded_data[key]
        
        data = await self._source.load_data(symbol, interval, start_time, end_time)
        self._loaded_data[key] = data
        
        return data
    
    def get_data_summary(self) -> Dict[str, Any]:
        """获取数据摘要"""
        summary = {
            "total_symbols": len(self.config.symbols),
            "total_intervals": len(self.config.intervals),
            "data_points": {},
            "total_points": 0,
        }
        
        for key, data in self._loaded_data.items():
            summary["data_points"][key] = len(data)
            summary["total_points"] += len(data)
        
        return summary
    
    def clear_cache(self):
        """清除缓存"""
        self._loaded_data.clear()
        if isinstance(self._source, FileDataSource):
            self._source.clear_cache()
    
    def get_loaded_data(self) -> Dict[str, List[KlineData]]:
        """获取已加载的数据"""
        return self._loaded_data.copy()


# 便捷函数
def create_data_loader(config: DataConfig) -> DataLoader:
    """创建数据加载器"""
    return DataLoader(config)
