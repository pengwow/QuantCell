"""
因子计算模块

提供量化交易因子计算和管理功能。

主要功能：
    - 因子列表管理：获取支持的因子列表
    - 因子计算：计算单因子或多因子值
    - 因子分析：IC分析、IR分析、单调性分析等
    - 因子验证：验证因子有效性

依赖模块：
    - qlib: 量化投资库，用于因子计算
    - common: 共享数据模型

使用示例：
    >>> from backend.factor import FactorService
    >>> service = FactorService()
    >>> factors = service.get_factor_list()
    >>> result = service.calculate_factor("momentum_5d", ["BTCUSDT"], "2023-01-01", "2023-12-31")

作者: QuantCell Team
创建日期: 2024-01-01
最后修改: 2024-01-01

版本: 1.0.0
"""

# 版本信息
__version__ = "1.0.0"
__author__ = "QuantCell Team"

# 导出主要组件
from .service import FactorService
from .routes import router
from .schemas import (
    FactorAddRequest,
    FactorCalculateRequest,
    FactorCalculateMultiRequest,
    FactorStatsRequest,
    FactorICRequest,
    FactorIRRequest,
    FactorCorrelationRequest,
    FactorValidateRequest,
    FactorStabilityRequest,
    FactorMonotonicityRequest,
    FactorGroupAnalysisRequest,
)

__all__ = [
    # 服务
    "FactorService",
    # 路由
    "router",
    # 请求模型
    "FactorAddRequest",
    "FactorCalculateRequest",
    "FactorCalculateMultiRequest",
    "FactorStatsRequest",
    "FactorICRequest",
    "FactorIRRequest",
    "FactorCorrelationRequest",
    "FactorValidateRequest",
    "FactorStabilityRequest",
    "FactorMonotonicityRequest",
    "FactorGroupAnalysisRequest",
]
