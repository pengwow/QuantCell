"""
数据质量检查模块

提供K线数据质量检查功能，支持从不同数据源（Parquet文件、数据库等）读取数据
并进行完整性、连续性、有效性、唯一性等质量检查。

主要组件：
- DataProvider: 数据提供者抽象接口
- ParquetDataProvider: Parquet 文件数据提供者实现
- KlineQualityService: K线质量检查核心服务

使用示例：
    from quality.parquet_provider import ParquetDataProvider
    from quality.kline_quality_service import KlineQualityService

    provider = ParquetDataProvider()
    service = KlineQualityService(provider)
    result = service.check_quality("BTCUSDT", "1h")
"""

from .data_provider import DataProvider
from .parquet_provider import ParquetDataProvider
from .kline_quality_service import KlineQualityService

__all__ = ['DataProvider', 'ParquetDataProvider', 'KlineQualityService']
