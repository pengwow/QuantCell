"""
系统设置模块

提供系统配置管理和系统信息查询功能。

主要功能:
    - 系统配置管理（增删改查）
    - 系统信息查询
    - 配置批量更新

模块结构:
    - service.py: 系统设置服务实现
    - routes.py: API路由定义
    - schemas.py: 数据模型定义
    - models.py: 数据库模型定义

使用示例:
    >>> from settings import SystemService, router
    >>> service = SystemService()
    >>> configs = service.get_all_configs()

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

__version__ = "1.0.0"
__author__ = "QuantCell Team"

from .services import SystemService
from .routes import router
from .schemas import (
    ConfigUpdateRequest,
    ConfigBatchUpdateRequest,
    SystemConfigItem,
    SystemConfigSimple,
    SystemInfo,
)
from .models import SystemConfigBusiness

__all__ = [
    "SystemService",
    "router",
    "ConfigUpdateRequest",
    "ConfigBatchUpdateRequest",
    "SystemConfigItem",
    "SystemConfigSimple",
    "SystemInfo",
    "SystemConfigBusiness",
]
