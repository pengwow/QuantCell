# 策略模块
# 提供策略管理和加载功能

from .service import StrategyService
from .routes import router_strategy
from .strategy_base import (
    StrategyBase,
    BacktestStrategyBase,
    LiveStrategyBase,
    StrategyParam,
    StrategyMetadata,
    Order,
    Position,
    StrategySignal
)
from .execution_engine import (
    ExecutionEngine,
    BacktestExecutionEngine,
    LiveExecutionEngine,
    ExecutionEngineFactory
)

# 新架构模块
from .core import UnifiedStrategyBase, EventEngine, EventType, VectorEngine
from .trading_modules import PerpetualContract, CryptoUtils
from .adapters import VectorBacktestAdapter

__all__ = [
    # 现有模块
    "StrategyService",
    "router_strategy",
    "StrategyBase",
    "BacktestStrategyBase",
    "LiveStrategyBase",
    "StrategyParam",
    "StrategyMetadata",
    "Order",
    "Position",
    "StrategySignal",
    "ExecutionEngine",
    "BacktestExecutionEngine",
    "LiveExecutionEngine",
    "ExecutionEngineFactory",
    # 新架构模块
    "UnifiedStrategyBase",
    "EventEngine",
    "EventType",
    "VectorEngine",
    "PerpetualContract",
    "CryptoUtils",
    "VectorBacktestAdapter"
]
