"""
策略模块

提供量化交易策略的管理、加载和执行功能。

主要功能:
    - 策略管理（增删改查）
    - 策略加载和解析
    - 策略执行（回测/实盘）
    - 策略验证
    - 多种执行引擎支持

模块结构:
    - service.py: 策略服务实现
    - routes.py: API路由定义
    - schemas.py: 数据模型定义
    - core/: 核心引擎模块
        - strategy_core.py: 策略核心类
        - strategy_base.py: 策略基类
        - event_engine.py: 事件驱动引擎
        - vector_engine.py: 向量化引擎
    - adapters/: 适配器模块
    - trading_modules/: 交易组件模块
    - validation/: 策略验证模块
    - example/: 示例和测试

使用示例:
    >>> from strategy import StrategyService, router
    >>> service = StrategyService()
    >>> strategies = service.get_strategy_list()

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

__version__ = "1.0.0"
__author__ = "QuantCell Team"

# 核心服务
from .service import StrategyService
from .routes import router
from .schemas import (
    StrategyInfo,
    StrategyParamInfo,
    StrategyListResponse,
    StrategyUploadRequest,
    StrategyUploadResponse,
    StrategyDetailRequest,
    StrategyDetailResponse,
    StrategyExecutionRequest,
    StrategyExecutionResponse,
    StrategyParseRequest,
    StrategyParseResponse,
    BacktestConfig,
)

# 策略基类
from .strategy_base import (
    StrategyBase,
    BacktestStrategyBase,
    LiveStrategyBase,
    StrategyParam,
    StrategyMetadata,
    Order,
    Position,
    StrategySignal,
)

# 执行引擎
from .execution_engine import (
    ExecutionEngine,
    BacktestExecutionEngine,
    LiveExecutionEngine,
    ExecutionEngineFactory,
)

# 新架构 - 核心引擎
from .core import (
    StrategyBase as StrategyCoreBase,
    EventEngine,
    EventType,
    VectorEngine,
    OptimizedEventEngine,
    AsyncEventEngine,
    ConcurrentEventEngine,
    BatchingEngine,
)

# 新架构 - 策略核心类
from .core.strategy_core import (
    StrategyCore,
    NativeVectorAdapter,
    StrategyRunner,
    StrategyAdapter,
)

# 新架构 - 适配器
from .adapters import VectorBacktestAdapter

# 新架构 - 交易组件
from .trading_modules import PerpetualContract, CryptoUtils

__all__ = [
    # 服务
    "StrategyService",
    "router",
    # 数据模型
    "StrategyInfo",
    "StrategyParamInfo",
    "StrategyListResponse",
    "StrategyUploadRequest",
    "StrategyUploadResponse",
    "StrategyDetailRequest",
    "StrategyDetailResponse",
    "StrategyExecutionRequest",
    "StrategyExecutionResponse",
    "StrategyParseRequest",
    "StrategyParseResponse",
    "BacktestConfig",
    # 策略基类
    "StrategyBase",
    "BacktestStrategyBase",
    "LiveStrategyBase",
    "StrategyParam",
    "StrategyMetadata",
    "Order",
    "Position",
    "StrategySignal",
    # 执行引擎
    "ExecutionEngine",
    "BacktestExecutionEngine",
    "LiveExecutionEngine",
    "ExecutionEngineFactory",
    # 新架构 - 核心引擎
    "StrategyCoreBase",
    "EventEngine",
    "EventType",
    "VectorEngine",
    "OptimizedEventEngine",
    "AsyncEventEngine",
    "ConcurrentEventEngine",
    "BatchingEngine",
    # 新架构 - 策略核心
    "StrategyCore",
    "NativeVectorAdapter",
    "StrategyRunner",
    "StrategyAdapter",
    # 新架构 - 适配器
    "VectorBacktestAdapter",
    # 新架构 - 交易组件
    "PerpetualContract",
    "CryptoUtils",
]
