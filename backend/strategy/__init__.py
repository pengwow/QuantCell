"""策略模块

提供量化交易策略的管理、加载和执行功能。
全部基于 axon_quant API。
"""

__version__ = "2.0.0"

from .loop import StrategyLoop
from .routes import router
from .schemas import (
    StrategyDetailRequest,
    StrategyInfo,
    StrategyListResponse,
    StrategyParamInfo,
    StrategyUploadRequest,
    StrategyUploadResponse,
)
from .service import StrategyService

__all__ = [
    "StrategyDetailRequest",
    "StrategyInfo",
    "StrategyListResponse",
    "StrategyLoop",
    "StrategyParamInfo",
    "StrategyService",
    "StrategyUploadRequest",
    "StrategyUploadResponse",
    "router",
]
