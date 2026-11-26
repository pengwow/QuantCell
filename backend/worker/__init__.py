"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - StrategyManager: 统一策略执行引擎
    - TradingNodeWorkerManager: 策略生命周期协调器
"""

from .manager import TradingNodeWorkerManager
from .routes import router
from .service import worker_service
from .strategy_manager import StrategyManager, worker_system

__all__ = [
    "StrategyManager",
    "TradingNodeWorkerManager",
    "router",
    "worker_service",
    "worker_system",
]
