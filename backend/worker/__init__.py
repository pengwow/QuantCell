"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - WorkerProcess: 基础 Worker 进程类
    - TradingNodeWorkerProcess: 支持 TradingNode 的 Worker 进程类
    - WorkerManager: Worker 管理器
    - TradingNodeWorkerManager: 支持 TradingNode 的 Worker 管理器
    - EventHandler: 事件处理器
    - config: 配置构建模块
"""

from .api import router
from .service import worker_service
from .worker_process import WorkerProcess, TradingNodeWorkerProcess
from .manager import WorkerManager, TradingNodeWorkerManager
from .event_handler import EventHandler, EventBufferConfig
from .config import (
    build_trading_node_config,
    build_binance_config,
    build_binance_live_config,
)

__all__ = [
    'router',
    'worker_service',
    'WorkerProcess',
    'TradingNodeWorkerProcess',
    'WorkerManager',
    'TradingNodeWorkerManager',
    'EventHandler',
    'EventBufferConfig',
    'build_trading_node_config',
    'build_binance_config',
    'build_binance_live_config',
]
