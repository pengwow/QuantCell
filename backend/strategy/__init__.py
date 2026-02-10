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

# 新架构模块 - 核心引擎
from .core import StrategyBase as StrategyCoreBase, EventEngine, EventType, VectorEngine
from .core import (
    OptimizedEventEngine,
    AsyncEventEngine,
    ConcurrentEventEngine,
    BatchingEngine
)

# 新架构模块 - 适配器
from .adapters import VectorBacktestAdapter

# 新架构模块 - 交易组件
from .trading_modules import PerpetualContract, CryptoUtils

# 核心策略类（与回测引擎无关）- 从 core.strategy_core 导入
from .core.strategy_core import (
    StrategyCore,
    NativeVectorAdapter,
    StrategyRunner,
    StrategyAdapter
)

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
    # 新架构模块 - 核心引擎
    "StrategyCoreBase",
    "EventEngine",
    "EventType",
    "VectorEngine",
    "OptimizedEventEngine",
    "AsyncEventEngine",
    "ConcurrentEventEngine",
    "BatchingEngine",
    # 新架构模块 - 适配器
    "VectorBacktestAdapter",
    # 新架构模块 - 交易组件
    "PerpetualContract",
    "CryptoUtils",
    # 核心策略类（与回测引擎无关）
    "StrategyCore",
    "NativeVectorAdapter",
    "StrategyRunner",
    "StrategyAdapter"
]
