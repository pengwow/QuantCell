"""策略模块

提供量化交易策略的管理、加载和执行功能。
全部基于 axon_quant API。

策略开发者一行 import 即可拿到全部核心类型：

    from strategy import Action, ActionType, BaseStrategy, StrategyConfig, StrategyContext
"""

__version__ = "3.0.0"

# 统一重导出 —— 策略开发者不需要感知 axon_bridge / axon_quant 底层
from axon_bridge import Action, ActionType

from .agent_traders import (
    EnsembleTrader,
    ReActTrader,
    StrategyTrader,
    TraderRegistry,
)
from .base import BaseStrategy, StrategyConfig, StrategyContext
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
    "Action",
    "ActionType",
    "BaseStrategy",
    "EnsembleTrader",
    "EventDrivenLoop",
    "ExecutionPipeline",
    "ExecutionResult",
    "LivePortfolio",
    "Position",
    "ReActTrader",
    "StrategyConfig",
    "StrategyContext",
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
