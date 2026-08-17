"""
策略执行引擎（TradingSystem）

替代原交易引擎，基于 axon-quant 事件驱动模型管理策略生命周期。
提供 start_strategy / stop_strategy 核心路径，供 WorkerCoreService 调用。

当前版本聚焦于策略状态管理（注册/启动/停止/状态转换），
实盘交易执行将在后续版本中接入 axon-quant 的实盘适配器。
"""

import asyncio
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from utils.logger import get_logger, LogType
from .state import strategy_registry
from .worker_state import worker_state_manager

logger = get_logger(__name__, LogType.APPLICATION)


class TradingSystem:
    """
    策略执行引擎（单例）

    管理策略的启动/停止生命周期，维护 strategy_registry 中的运行时状态。
    通过 worker_state_manager 驱动状态转换事件。
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def initialize(self) -> bool:
        """初始化策略执行引擎"""
        if self._initialized:
            return True
        self._initialized = True
        logger.info("[TradingSystem] 策略执行引擎初始化完成")
        return True

    async def start_strategy(self, worker_id: int) -> bool:
        """
        启动策略

        从 strategy_registry 获取运行时对象，执行状态转换并标记为运行中。

        Args:
            worker_id: Worker ID

        Returns:
            是否启动成功
        """
        if not self._initialized:
            logger.warning("[TradingSystem] 引擎未初始化，无法启动策略")
            return False

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            logger.warning(f"[TradingSystem] Worker {worker_id} 不在注册表中")
            return False

        # 已在运行中（状态为 running 或有存活的任务/线程）则拒绝重复启动
        if runtime.status == "running" or runtime.is_running:
            logger.warning(f"[TradingSystem] Worker {worker_id} 已在运行中")
            return False

        try:
            await worker_state_manager.transition(worker_id, "starting")

            # 更新运行时状态
            runtime.started_at = datetime.now(timezone.utc).isoformat()
            runtime.error_message = None
            strategy_registry.update_status(worker_id, "running")

            await worker_state_manager.transition(worker_id, "running")

            logger.info(f"[TradingSystem] 策略已启动: worker_id={worker_id}")
            return True

        except Exception as e:
            logger.error(f"[TradingSystem] 启动策略失败: worker_id={worker_id}, error={e}")
            await worker_state_manager.transition(
                worker_id, "error", error_message=str(e)
            )
            return False

    async def stop_strategy(self, worker_id: int) -> bool:
        """
        停止策略

        从 strategy_registry 获取运行时对象，执行状态转换并标记为已停止。

        Args:
            worker_id: Worker ID

        Returns:
            是否停止成功
        """
        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            logger.warning(f"[TradingSystem] Worker {worker_id} 不在注册表中")
            return False

        if runtime.status == "stopped":
            logger.info(f"[TradingSystem] Worker {worker_id} 已处于 stopped 状态")
            return True

        try:
            await worker_state_manager.transition(worker_id, "stopping")

            # 取消运行中的任务
            if runtime._run_task is not None and not runtime._run_task.done():
                runtime._run_task.cancel()

            # 更新运行时状态
            runtime.stopped_at = datetime.now(timezone.utc).isoformat()
            strategy_registry.update_status(worker_id, "stopped")

            await worker_state_manager.transition(worker_id, "stopped")

            logger.info(f"[TradingSystem] 策略已停止: worker_id={worker_id}")
            return True

        except Exception as e:
            logger.error(f"[TradingSystem] 停止策略失败: worker_id={worker_id}, error={e}")
            return False


# 模块级单例实例
trading_system = TradingSystem()


def _register_into_state() -> None:
    """
    将单例注册到 state.py 全局枢纽

    trading_system.py 依赖 state.py（导入 strategy_registry），
    因此不能在 state.py 顶部直接导入本模块（会循环依赖）。
    改为在本模块加载完成后反向写入 state.trading_system。
    """
    from . import state as _ws
    _ws.trading_system = trading_system


_register_into_state()
