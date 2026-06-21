"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - AxonTradingSystem: 基于 axon_quant 的策略执行引擎（推荐）
    - TradingNodeWorkerManager: 策略生命周期协调器（纯 asyncio 事件驱动）
    - EventHandler: 事件处理器
    - config: 配置构建模块
"""

from .routes import router
from .service import worker_service
from .manager import TradingNodeWorkerManager
from .event_handler import EventHandler, EventBufferConfig

# axon_quant 相关导入
from .axon_worker_system import AxonTradingSystem, worker_system

# nautilus_trader 相关导入（可选）
try:
    from .config import (
        build_trading_node_config,
        build_binance_config,
        build_binance_live_config,
    )
    NAUTILUS_CONFIG_AVAILABLE = True
except ImportError:
    NAUTILUS_CONFIG_AVAILABLE = False
    build_trading_node_config = None
    build_binance_config = None
    build_binance_live_config = None

__all__ = [
    'router',
    'worker_service',
    'AxonTradingSystem',
    'worker_system',
    'TradingNodeWorkerManager',
    'EventHandler',
    'EventBufferConfig',
    'build_trading_node_config',
    'build_binance_config',
    'build_binance_live_config',
    'NAUTILUS_CONFIG_AVAILABLE',
]
