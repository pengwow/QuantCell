"""
数据采集模块

提供多市场、多品种的数据采集功能。

主要功能:
    - 加密货币数据采集(Binance, OKX)
    - 股票数据采集
    - 数据池管理
    - 定时任务调度
    - 数据质量监控

模块结构:
    - api/: API路由层
        - config.py: 配置管理
        - data.py: 数据操作
        - data_pool.py: 数据池管理
        - scheduled_tasks.py: 定时任务
        - system.py: 系统管理
    - db/: 数据库层
        - connection.py: 连接管理
        - crud.py: CRUD操作
        - database.py: 数据库实例
        - migrations.py: 迁移脚本
        - models.py: 数据模型
        - schemas.py: Pydantic模型
    - schemas/: 数据模型定义
        - data.py: 数据相关模型
        - system.py: 系统相关模型
    - scripts/: 工具脚本
        - convert_to_qlib.py: QLib格式转换
        - export_data.py: 数据导出
        - export_kline.py: K线导出
        - get_data.py: 数据获取
    - services/: 业务服务层
        - crypto_symbol_service.py: 币种服务
        - data_service.py: 数据服务
        - kline_factory.py: K线工厂
        - kline_health_service.py: 数据健康检查
        - product_factory.py: 产品工厂
        - system_service.py: 系统服务
    - utils/: 工具模块
        - scheduled_task_manager.py: 定时任务管理
        - task_manager.py: 任务管理
    - routes.py: 主路由入口

使用示例:
    >>> from collector import router
    >>> from collector.services import DataService

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

__version__ = "1.0.0"
__author__ = "QuantCell Team"

from .routes import router
from .services import (
    DataService,
    CryptoSymbolService,
    KlineDataFactory,
    KlineHealthChecker,
    ProductListFactory,
    SystemService,
)

__all__ = [
    # 路由
    "router",
    # 服务
    "DataService",
    "CryptoSymbolService",
    "KlineDataFactory",
    "KlineHealthChecker",
    "ProductListFactory",
    "SystemService",
]
