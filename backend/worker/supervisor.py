"""
Worker 监控器模块

提供 Worker 进程监控、健康检查和自动重启功能
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from loguru import logger

from .state import WorkerState, WorkerStatus


@dataclass
class RestartPolicy:
    """重启策略配置"""

    max_restarts: int = 3  # 最大重启次数
    restart_window: int = 300  # 重启窗口时间（秒）
    backoff_base: float = 1.0  # 退避基数（秒）
    backoff_max: float = 60.0  # 最大退避时间（秒）


@dataclass
class HealthCheckConfig:
    """健康检查配置"""

    heartbeat_timeout: int = 30  # 心跳超时时间（秒）
    check_interval: int = 10  # 检查间隔（秒）
    unhealthy_threshold: int = 3  # 不健康阈值


class WorkerSupervisor:
    """
    Worker 监控器

    负责：
    - 监控 Worker 健康状态
    - 自动重启故障 Worker
    - 记录重启历史
    - 提供健康报告
    """

    def __init__(
        self,
        restart_policy: Optional[RestartPolicy] = None,
        health_config: Optional[HealthCheckConfig] = None,
    ):
        """
        初始化监控器

        Args:
            restart_policy: 重启策略
            health_config: 健康检查配置
        """
        self.restart_policy = restart_policy or RestartPolicy()
        self.health_config = health_config or HealthCheckConfig()

        # Worker 状态跟踪
        self._worker_status: Dict[str, WorkerStatus] = {}
        self._heartbeat_history: Dict[str, List[datetime]] = {}
        self._restart_history: Dict[str, List[datetime]] = {}
        self._unhealthy_count: Dict[str, int] = {}

        # 回调函数
        self._health_handlers: List[Callable[[str, bool], None]] = []
        self._restart_handlers: List[Callable[[str, int], None]] = []

        # 运行状态
        self._running = False
        self._check_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """
        启动监控器

        Returns:
            是否启动成功
        """
        try:
            self._running = True
            self._check_task = asyncio.create_task(self._health_check_loop())
            logger.info("Worker 监控器已启动")
            return True
        except Exception as e:
            logger.error(f"启动监控器失败: {e}")
            return False

    async def stop(self) -> bool:
        """
        停止监控器

        Returns:
            是否停止成功
        """
        self._running = False

        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

        logger.info("Worker 监控器已停止")
        return True

    def register_worker(self, worker_id: str, status: WorkerStatus):
        """
        注册 Worker 到监控器

        Args:
            worker_id: Worker ID
            status: Worker 状态
        """
        self._worker_status[worker_id] = status
        self._heartbeat_history[worker_id] = []
        self._restart_history[worker_id] = []
        self._unhealthy_count[worker_id] = 0
        logger.debug(f"Worker {worker_id} 已注册到监控器")

    def unregister_worker(self, worker_id: str):
        """
        从监控器注销 Worker

        Args:
            worker_id: Worker ID
        """
        if worker_id in self._worker_status:
            del self._worker_status[worker_id]
        if worker_id in self._heartbeat_history:
            del self._heartbeat_history[worker_id]
        if worker_id in self._restart_history:
            del self._restart_history[worker_id]
        if worker_id in self._unhealthy_count:
            del self._unhealthy_count[worker_id]
        logger.debug(f"Worker {worker_id} 已从监控器注销")

    def update_heartbeat(self, worker_id: str):
        """
        更新 Worker 心跳

        Args:
            worker_id: Worker ID
        """
        now = datetime.now()

        if worker_id not in self._heartbeat_history:
            self._heartbeat_history[worker_id] = []

        self._heartbeat_history[worker_id].append(now)

        # 只保留最近的心跳记录
        cutoff = now - timedelta(seconds=self.health_config.heartbeat_timeout * 2)
        self._heartbeat_history[worker_id] = [
            t for t in self._heartbeat_history[worker_id] if t > cutoff
        ]

        # 同时更新 WorkerStatus 的心跳时间
        if worker_id in self._worker_status:
            self._worker_status[worker_id].update_heartbeat()

        # 重置不健康计数
        if worker_id in self._unhealthy_count:
            self._unhealthy_count[worker_id] = 0

    def record_restart(self, worker_id: str):
        """
        记录 Worker 重启

        Args:
            worker_id: Worker ID
        """
        now = datetime.now()

        if worker_id not in self._restart_history:
            self._restart_history[worker_id] = []

        self._restart_history[worker_id].append(now)

        # 只保留重启窗口内的记录
        cutoff = now - timedelta(seconds=self.restart_policy.restart_window)
        self._restart_history[worker_id] = [
            t for t in self._restart_history[worker_id] if t > cutoff
        ]

        restart_count = len(self._restart_history[worker_id])
        logger.info(f"Worker {worker_id} 已重启 {restart_count} 次")

        # 调用重启处理器
        for handler in self._restart_handlers:
            try:
                handler(worker_id, restart_count)
            except Exception as e:
                logger.error(f"重启处理器错误: {e}")

    def is_healthy(self, worker_id: str) -> bool:
        """
        检查 Worker 是否健康

        Args:
            worker_id: Worker ID

        Returns:
            是否健康
        """
        if worker_id not in self._worker_status:
            return False

        status = self._worker_status[worker_id]

        # 检查状态
        if status.state not in [WorkerState.RUNNING, WorkerState.PAUSED]:
            return False

        # 检查心跳
        if status.last_heartbeat is None:
            return False

        elapsed = datetime.now() - status.last_heartbeat
        return elapsed < timedelta(seconds=self.health_config.heartbeat_timeout)

    def should_restart(self, worker_id: str) -> bool:
        """
        检查是否应该重启 Worker

        Args:
            worker_id: Worker ID

        Returns:
            是否应该重启
        """
        if worker_id not in self._restart_history:
            return True

        restart_count = len(self._restart_history[worker_id])
        return restart_count < self.restart_policy.max_restarts

    def get_restart_delay(self, worker_id: str) -> float:
        """
        获取重启延迟时间（指数退避）

        Args:
            worker_id: Worker ID

        Returns:
            延迟时间（秒）
        """
        if worker_id not in self._restart_history:
            return 0.0

        restart_count = len(self._restart_history[worker_id])
        if restart_count == 0:
            return 0.0

        delay = self.restart_policy.backoff_base * (2 ** (restart_count - 1))
        return min(delay, self.restart_policy.backoff_max)

    def get_health_report(self, worker_id: str) -> Optional[dict]:
        """
        获取 Worker 健康报告

        Args:
            worker_id: Worker ID

        Returns:
            健康报告或 None
        """
        if worker_id not in self._worker_status:
            return None

        status = self._worker_status[worker_id]
        restart_count = len(self._restart_history.get(worker_id, []))
        heartbeat_count = len(self._heartbeat_history.get(worker_id, []))

        return {
            "worker_id": worker_id,
            "state": status.state.value,
            "is_healthy": self.is_healthy(worker_id),
            "restart_count": restart_count,
            "heartbeat_count": heartbeat_count,
            "last_heartbeat": status.last_heartbeat.isoformat() if status.last_heartbeat else None,
            "errors_count": status.errors_count,
            "last_error": status.last_error,
        }

    def get_all_health_reports(self) -> Dict[str, dict]:
        """
        获取所有 Worker 的健康报告

        Returns:
            Worker ID -> 健康报告 的字典
        """
        return {
            worker_id: self.get_health_report(worker_id)
            for worker_id in self._worker_status.keys()
        }

    def register_health_handler(self, handler: Callable[[str, bool], None]):
        """
        注册健康状态变化处理器

        Args:
            handler: 处理函数，接收 (worker_id, is_healthy) 参数
        """
        self._health_handlers.append(handler)

    def unregister_health_handler(self, handler: Callable[[str, bool], None]):
        """
        注销健康状态变化处理器

        Args:
            handler: 处理函数
        """
        if handler in self._health_handlers:
            self._health_handlers.remove(handler)

    def register_restart_handler(self, handler: Callable[[str, int], None]):
        """
        注册重启处理器

        Args:
            handler: 处理函数，接收 (worker_id, restart_count) 参数
        """
        self._restart_handlers.append(handler)

    async def _health_check_loop(self):
        """
        健康检查循环

        定期检查所有 Worker 的健康状态
        """
        while self._running:
            try:
                for worker_id in list(self._worker_status.keys()):
                    await self._check_worker_health(worker_id)

                await asyncio.sleep(self.health_config.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")
                await asyncio.sleep(self.health_config.check_interval)

    async def _check_worker_health(self, worker_id: str):
        """
        检查单个 Worker 的健康状态

        Args:
            worker_id: Worker ID
        """
        if worker_id not in self._worker_status:
            return

        is_healthy = self.is_healthy(worker_id)

        if not is_healthy:
            # 增加不健康计数
            if worker_id not in self._unhealthy_count:
                self._unhealthy_count[worker_id] = 0
            self._unhealthy_count[worker_id] += 1

            logger.warning(
                f"Worker {worker_id} 不健康，计数: {self._unhealthy_count[worker_id]}"
            )

            # 调用健康处理器
            for handler in self._health_handlers:
                try:
                    handler(worker_id, False)
                except Exception as e:
                    logger.error(f"健康处理器错误: {e}")
        else:
            # 健康状态良好
            if worker_id in self._unhealthy_count and self._unhealthy_count[worker_id] > 0:
                self._unhealthy_count[worker_id] = 0
                logger.info(f"Worker {worker_id} 恢复健康")

                # 调用健康处理器
                for handler in self._health_handlers:
                    try:
                        handler(worker_id, True)
                    except Exception as e:
                        logger.error(f"健康处理器错误: {e}")

    def is_restart_recommended(self, worker_id: str) -> bool:
        """
        检查是否建议重启 Worker

        Args:
            worker_id: Worker ID

        Returns:
            是否建议重启
        """
        if worker_id not in self._unhealthy_count:
            return False

        return self._unhealthy_count[worker_id] >= self.health_config.unhealthy_threshold

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        total_workers = len(self._worker_status)
        healthy_workers = sum(
            1 for wid in self._worker_status if self.is_healthy(wid)
        )
        unhealthy_workers = total_workers - healthy_workers

        total_restarts = sum(
            len(restarts) for restarts in self._restart_history.values()
        )

        return {
            "total_workers": total_workers,
            "healthy_workers": healthy_workers,
            "unhealthy_workers": unhealthy_workers,
            "total_restarts": total_restarts,
            "restart_policy": {
                "max_restarts": self.restart_policy.max_restarts,
                "restart_window": self.restart_policy.restart_window,
            },
            "health_config": {
                "heartbeat_timeout": self.health_config.heartbeat_timeout,
                "check_interval": self.health_config.check_interval,
            },
        }
