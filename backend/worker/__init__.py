"""
Worker 进程管理模块

提供独立进程运行策略的能力，包括：
- Worker 进程管理
- 进程间通信
- 数据订阅和分发
- 进程池管理
- 进程监控和故障恢复

使用示例:
    ```python
    from worker import WorkerManager

    # 创建并启动管理器
    manager = WorkerManager(max_workers=10)
    await manager.start()

    # 启动策略
    worker_id = await manager.start_strategy(
        strategy_path="/path/to/strategy.py",
        config={
            "symbols": ["BTC/USDT", "ETH/USDT"],
            "params": {"n1": 10, "n2": 20}
        }
    )

    # 发布市场数据
    await manager.publish_market_data(
        symbol="BTC/USDT",
        data_type="kline",
        data={"open": 50000, "high": 51000, "low": 49000, "close": 50500}
    )

    # 停止策略
    await manager.stop_worker(worker_id)

    # 停止管理器
    await manager.stop()
    ```
"""

from .state import WorkerState, WorkerStatus, StateMachine
from .worker_process import WorkerProcess
from .manager import WorkerManager
from .pool import ProcessPool, PoolConfig
from .supervisor import WorkerSupervisor, RestartPolicy, HealthCheckConfig
from .ipc import (
    MessageType,
    Message,
    CommManager,
    WorkerCommClient,
    DataBroker,
    DataSubscription,
)

__all__ = [
    # 状态管理
    "WorkerState",
    "WorkerStatus",
    "StateMachine",
    # Worker 进程
    "WorkerProcess",
    # 管理器
    "WorkerManager",
    # 进程池
    "ProcessPool",
    "PoolConfig",
    # 监控器
    "WorkerSupervisor",
    "RestartPolicy",
    "HealthCheckConfig",
    # IPC 组件
    "MessageType",
    "Message",
    "CommManager",
    "WorkerCommClient",
    "DataBroker",
    "DataSubscription",
]

__version__ = "0.1.0"
