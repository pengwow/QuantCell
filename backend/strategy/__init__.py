"""策略模块

提供量化交易策略的管理、加载和执行功能。
全部基于 axon_quant API。
"""

__version__ = "3.0.0"

from .agent_traders import (
    EnsembleTrader,
    ReActTrader,
    StrategyTrader,
    TraderRegistry,
)
from .event_loop import EventDrivenLoop
from .execution_pipeline import ExecutionPipeline, ExecutionResult
from .live_portfolio import LivePortfolio, Position
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
    "EnsembleTrader",
    "EventDrivenLoop",
    "ExecutionPipeline",
    "ExecutionResult",
    "LivePortfolio",
    "Position",
    "ReActTrader",
    "StrategyDetailRequest",
    "StrategyInfo",
    "StrategyListResponse",
    "StrategyLoop",
    "StrategyParamInfo",
    "StrategyService",
    "StrategyTrader",
    "StrategyUploadRequest",
    "StrategyUploadResponse",
    "TraderRegistry",
    "router",
]
