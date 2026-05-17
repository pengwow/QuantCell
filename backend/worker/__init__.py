"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - WorkerProcess: 基础 Worker 进程类
    - TradingNodeWorkerProcess: 支持 TradingNode 的 Worker 进程类
    - TradingNodeWorkerManager: 策略生命周期协调器（纯 asyncio 事件驱动）
    - EventHandler: 事件处理器
    - config: 配置构建模块
"""

from .api import router
from .service import worker_service
from .manager import TradingNodeWorkerManager
from .event_handler import EventHandler, EventBufferConfig
from .config import (
    build_trading_node_config,
    build_binance_config,
    build_binance_live_config,
)

__all__ = [
    'router',
    'worker_service',
    'TradingNodeWorkerManager',
    'EventHandler',
    'EventBufferConfig',
    'build_trading_node_config',
    'build_binance_config',
    'build_binance_live_config',
]
