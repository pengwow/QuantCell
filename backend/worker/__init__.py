"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - StrategyManager: 统一策略执行引擎
    - TradingNodeWorkerManager: 策略生命周期协调器
    - EventHandler: 事件处理器
"""

from .routes import router
from .service import worker_service
from .manager import TradingNodeWorkerManager
from .event_handler import EventHandler, EventBufferConfig
from .trading_system import TradingSystem, trading_system
from .strategy_manager import StrategyManager, worker_system

__all__ = [
    'router',
    'worker_service',
    'StrategyManager',
    'worker_system',
    'TradingNodeWorkerManager',
    'EventHandler',
    'EventBufferConfig',
    'TradingSystem',
    'trading_system',
]
