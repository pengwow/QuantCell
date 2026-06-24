"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - AxonTradingSystem: 基于 axon_quant 的策略执行引擎
    - TradingNodeWorkerManager: 策略生命周期协调器
    - EventHandler: 事件处理器
"""

from .routes import router
from .service import worker_service
from .manager import TradingNodeWorkerManager
from .event_handler import EventHandler, EventBufferConfig
from .axon_worker_system import AxonTradingSystem, worker_system

__all__ = [
    'router',
    'worker_service',
    'AxonTradingSystem',
    'worker_system',
    'TradingNodeWorkerManager',
    'EventHandler',
    'EventBufferConfig',
]
