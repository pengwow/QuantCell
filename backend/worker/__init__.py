"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - StrategyManager: 统一策略执行引擎
    - TradingNodeWorkerManager: 策略生命周期协调器
    - EventHandler: 事件处理器
"""

from .event_handler import EventBufferConfig, EventHandler
from .manager import TradingNodeWorkerManager
from .routes import router
from .service import worker_service
from .strategy_manager import StrategyManager, worker_system
from .trading_system import TradingSystem, trading_system

__all__ = [
    "EventBufferConfig",
    "EventHandler",
    "StrategyManager",
    "TradingNodeWorkerManager",
    "TradingSystem",
    "router",
    "trading_system",
    "worker_service",
    "worker_system",
]
