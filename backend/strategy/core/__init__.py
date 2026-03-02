# 策略接口
from .data_types import (
    Bar,
    InstrumentId,
    Order,
    Position,
    AccountBalance,
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
    QuoteTick,
    TradeTick,
)
from .strategy import (
    StrategyBase,
    StrategyConfig,
    Strategy,
)

# 核心引擎模块
from .strategy import Strategy as LegacyStrategy, StrategyConfig as LegacyStrategyConfig, StrategyBase as LegacyStrategyBase
from .event_engine import EventEngine, EventType
from .vector_engine import VectorEngine
from .numba_functions import (
    simulate_orders,
    signals_to_orders,
    calculate_metrics,
    calculate_funding_rate,
    calculate_funding_payment
)

# 优化的事件引擎
from .event_engine_optimized import (
    OptimizedEventEngine,
    EventPriority,
    BoundedPriorityQueue,
    EventMetrics,
    create_optimized_engine
)

# 异步事件引擎
from .async_event_engine import (
    AsyncEventEngine,
    AsyncPrioritizedEvent,
    AsyncBoundedPriorityQueue,
    AsyncEventMetrics,
    create_async_engine
)

# 并发事件引擎
from .concurrent_event_engine import (
    ConcurrentEventEngine,
    SymbolShard,
    SymbolEvent,
    ConcurrentEventMetrics,
    create_concurrent_engine
)

# 批处理引擎
from .batching_engine import (
    BatchingEngine,
    BatchEvent,
    EventBatch,
    BatchStrategy,
    VectorizedBatchProcessor,
    create_batching_engine
)

# 内存池
from .memory_pool import (
    ObjectPool,
    PooledObject,
    TickEvent,
    BarEvent,
    EventObjectPools,
    SharedMemoryMarketData,
    PreallocatedBuffers,
    get_event_pools,
    create_tick_event,
    create_bar_event
)

# 硬件优化器
from .hardware_optimizer import (
    NUMAOptimizer,
    ThreadAffinityManager,
    CacheOptimizer,
    HardwareInfo,
    CPUMonitor,
    create_numa_optimizer,
    create_thread_affinity_manager,
    pin_current_thread_to_core,
    get_optimal_core_count
)

# 弹性机制（边界情况处理）
from .resilience import (
    GracefulDegradation,
    ExceptionIsolation,
    CircuitBreaker,
    AutoScaler,
    EventPriority,
    DegradationLevel,
    CircuitBreakerState,
    create_resilience_manager
)

# 策略核心类（从 strategy/core.py 迁移）
from .strategy_core import (
    StrategyCore,
    StrategyAdapter,
    NativeVectorAdapter,
    StrategyRunner
)

__all__ = [
    # 策略接口
    "Bar",
    "InstrumentId",
    "Order",
    "Position",
    "AccountBalance",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "PositionSide",
    "QuoteTick",
    "TradeTick",
    "StrategyBase",
    "StrategyConfig",
    "Strategy",

    # 基础组件
    "LegacyStrategy",
    "LegacyStrategyConfig",
    "LegacyStrategyBase",
    "EventEngine",
    "EventType",
    "VectorEngine",

    # Numba函数
    "simulate_orders",
    "signals_to_orders",
    "calculate_metrics",
    "calculate_funding_rate",
    "calculate_funding_payment",

    # 优化的事件引擎
    "OptimizedEventEngine",
    "EventPriority",
    "BoundedPriorityQueue",
    "EventMetrics",
    "create_optimized_engine",

    # 异步事件引擎
    "AsyncEventEngine",
    "AsyncPrioritizedEvent",
    "AsyncBoundedPriorityQueue",
    "AsyncEventMetrics",
    "create_async_engine",

    # 并发事件引擎
    "ConcurrentEventEngine",
    "SymbolShard",
    "SymbolEvent",
    "ConcurrentEventMetrics",
    "create_concurrent_engine",

    # 批处理引擎
    "BatchingEngine",
    "BatchEvent",
    "EventBatch",
    "BatchStrategy",
    "VectorizedBatchProcessor",
    "create_batching_engine",

    # 内存池
    "ObjectPool",
    "PooledObject",
    "TickEvent",
    "BarEvent",
    "EventObjectPools",
    "SharedMemoryMarketData",
    "PreallocatedBuffers",
    "get_event_pools",
    "create_tick_event",
    "create_bar_event",

    # 硬件优化器
    "NUMAOptimizer",
    "ThreadAffinityManager",
    "CacheOptimizer",
    "HardwareInfo",
    "CPUMonitor",
    "create_numa_optimizer",
    "create_thread_affinity_manager",
    "pin_current_thread_to_core",
    "get_optimal_core_count",

    # 弹性机制（边界情况处理）
    "GracefulDegradation",
    "ExceptionIsolation",
    "CircuitBreaker",
    "AutoScaler",
    "EventPriority",
    "DegradationLevel",
    "CircuitBreakerState",
    "create_resilience_manager",

    # 策略核心类
    "StrategyCore",
    "StrategyAdapter",
    "NativeVectorAdapter",
    "StrategyRunner"
]
