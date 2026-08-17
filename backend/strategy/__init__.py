# -*- coding: utf-8 -*-
"""策略模块

提供量化交易策略的管理、加载和执行功能。
全部基于 axon_quant API。
"""

__version__ = "2.0.0"

from .service import StrategyService
from .routes import router
from .schemas import (
    StrategyInfo,
    StrategyParamInfo,
    StrategyListResponse,
    StrategyUploadRequest,
    StrategyUploadResponse,
    StrategyDetailRequest,
)
from .loop import StrategyLoop

__all__ = [
    "StrategyService",
    "router",
    "StrategyLoop",
    "StrategyInfo",
    "StrategyParamInfo",
    "StrategyListResponse",
    "StrategyUploadRequest",
    "StrategyUploadResponse",
    "StrategyDetailRequest",
]
