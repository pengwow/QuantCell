"""
回测引擎配置设置

定义回测引擎的配置常量和默认设置。

包含:
    - EngineType: 引擎类型枚举 (从 base 模块导入)
    - DEFAULT_ENGINE: 默认引擎类型
    - DEFAULT_CONFIG: 默认引擎配置

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

from typing import Any, Dict

# 从 base 模块导入 EngineType，确保只有一个定义
from backtest.engines.base import EngineType


# 默认引擎类型
DEFAULT_ENGINE: EngineType = EngineType.DEFAULT

# 默认引擎配置
DEFAULT_CONFIG: Dict[str, Any] = {
    # 日志级别: DEBUG, INFO, WARNING, ERROR
    "log_level": "INFO",
    # 缓存配置
    "cache": {
        # 是否启用缓存
        "enabled": True,
        # 缓存大小限制(MB)
        "size_mb": 512,
        # 缓存过期时间(秒)
        "ttl_seconds": 3600,
    },
}
