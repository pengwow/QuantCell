"""
策略生命周期协调器（纯 asyncio 事件驱动）

管理策略的启动/停止/健康检查，不再管理进程
响应 worker_state_manager 的状态变更事件
"""

import asyncio
from typing import Optional

from utils.logger import get_logger, LogType
from .worker_state import worker_state_manager
from .state import nautilus_system, strategy_registry

logger = get_logger(__name__, LogType.APPLICATION)


class TradingNodeWorkerManager:

    def __init__(self, enable_monitoring: bool = True):
        self.enable_monitoring = enable_monitoring
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None

        worker_state_manager.register_handler("state_changed", self._on_state_changed)
        logger.info("TradingNodeWorkerManager 已初始化为纯 asyncio 策略协调器")

    async def initialize(self) -> bool:
        try:
            self._running = True
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("策略协调器已启动")
            return True
        except Exception as e:
            logger.error(f"启动策略协调器失败: {e}")
            return False

    async def start(self) -> bool:
        return await self.initialize()

    async def stop(self) -> bool:
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("策略协调器已停止")
        return True

    async def _on_state_changed(self, event_data: dict):
        worker_id = event_data["worker_id"]
        new_status = event_data["new_status"]
        old_status = event_data.get("old_status", "unknown")

        logger.info(
            f"[事件驱动] 状态变更 | worker_id={worker_id} | "
            f"{old_status} -> {new_status}"
        )

        try:
            if new_status == "starting":
                await self._handle_start_event(worker_id)
            elif new_status == "stopping":
                await self._handle_stop_event(worker_id)
        except Exception as e:
            logger.error(
                f"[事件驱动] 处理事件失败 | worker_id={worker_id} | error={e}"
            )

    async def _handle_start_event(self, worker_id: int):
        logger.info(f"[启动事件] Worker {worker_id} 启动策略")
        try:
            if nautilus_system is not None:
                nautilus_system.start_strategy(worker_id)
            strategy_registry.update_status(worker_id, "running")
            logger.info(f"[启动事件] Worker {worker_id} 策略已启动")
        except Exception as e:
            logger.error(f"[启动事件] Worker {worker_id} 启动失败: {e}")

    async def _handle_stop_event(self, worker_id: int):
        logger.info(f"[停止事件] Worker {worker_id} 停止策略")
        try:
            if nautilus_system is not None:
                nautilus_system.stop_strategy(worker_id)
            strategy_registry.update_status(worker_id, "stopped")
            logger.info(f"[停止事件] Worker {worker_id} 策略已停止")
        except Exception as e:
            logger.error(f"[停止事件] Worker {worker_id} 停止失败: {e}")

    async def _health_check_loop(self):
        logger.info("[健康检查] 循环已启动，间隔 30 秒")
        while self._running:
            try:
                await asyncio.sleep(30)
                await self._check_strategy_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[健康检查] 循环异常: {e}")
                await asyncio.sleep(60)

    async def _check_strategy_health(self):
        runtimes = strategy_registry.list_all()
        for runtime in runtimes:
            try:
                if runtime.status == "running" and not runtime.is_running:
                    logger.warning(
                        f"[健康检查] Worker {runtime.worker_id} 状态不一致 "
                        f"(status=running, is_running=False)，修正为 stopped"
                    )
                    strategy_registry.update_status(runtime.worker_id, "stopped")
            except Exception as e:
                logger.error(
                    f"[健康检查] 检查 Worker {runtime.worker_id} 失败: {e}"
                )