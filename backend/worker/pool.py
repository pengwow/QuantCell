"""
进程池管理模块

提供进程池功能，预创建 Worker 进程以减少启动延迟
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

from .worker_process import WorkerProcess
from .state import WorkerState, WorkerStatus


@dataclass
class PoolConfig:
    """进程池配置"""

    min_size: int = 2  # 最小进程数
    max_size: int = 10  # 最大进程数
    idle_timeout: int = 300  # 空闲超时时间（秒）
    max_restarts: int = 3  # 最大重启次数
    restart_interval: int = 60  # 重启间隔（秒）


class ProcessPool:
    """
    进程池

    管理预创建的 Worker 进程，提供快速分配和回收功能
    """

    def __init__(
        self,
        config: Optional[PoolConfig] = None,
        comm_host: str = "127.0.0.1",
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
    ):
        """
        初始化进程池

        Args:
            config: 进程池配置
            comm_host: 通信主机地址
            data_port: 数据端口
            control_port: 控制端口
            status_port: 状态端口
        """
        self.config = config or PoolConfig()
        self.comm_host = comm_host
        self.data_port = data_port
        self.control_port = control_port
        self.status_port = status_port

        # 进程池
        self._available: List[WorkerProcess] = []  # 可用进程
        self._in_use: Dict[str, WorkerProcess] = {}  # 正在使用的进程
        self._worker_metadata: Dict[str, dict] = {}  # Worker 元数据

        # 统计信息
        self._created_count = 0
        self._reused_count = 0
        self._released_count = 0

        # 运行状态
        self._running = False
        self._maintenance_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """
        启动进程池

        Returns:
            是否启动成功
        """
        try:
            self._running = True

            # 预创建最小数量的进程
            for _ in range(self.config.min_size):
                worker = await self._create_idle_worker()
                if worker:
                    self._available.append(worker)

            # 启动维护任务
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())

            logger.info(
                f"进程池已启动，预创建 {len(self._available)} 个 Worker"
            )
            return True

        except Exception as e:
            logger.error(f"启动进程池失败: {e}")
            await self.stop()
            return False

    async def stop(self) -> bool:
        """
        停止进程池

        Returns:
            是否停止成功
        """
        self._running = False

        # 取消维护任务
        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass

        # 停止所有进程
        all_workers = self._available + list(self._in_use.values())
        for worker in all_workers:
            await self._stop_worker(worker)

        self._available.clear()
        self._in_use.clear()
        self._worker_metadata.clear()

        logger.info("进程池已停止")
        return True

    async def acquire(
        self,
        strategy_path: str,
        config: Dict[str, Any],
        worker_id: Optional[str] = None,
    ) -> Optional[WorkerProcess]:
        """
        获取一个 Worker 进程

        Args:
            strategy_path: 策略文件路径
            config: 策略配置
            worker_id: 可选的 Worker ID

        Returns:
            Worker 进程或 None
        """
        try:
            # 检查是否已达到最大进程数
            total_workers = len(self._available) + len(self._in_use)
            if total_workers >= self.config.max_size:
                logger.warning(f"进程池已满，无法分配新 Worker")
                return None

            # 尝试从可用列表获取
            worker = None
            if self._available:
                worker = self._available.pop(0)
                self._reused_count += 1
                logger.debug(f"复用现有 Worker: {worker.worker_id}")

            # 如果没有可用进程，创建新进程
            if worker is None:
                worker = await self._create_worker(strategy_path, config, worker_id)
                if worker is None:
                    return None
                self._created_count += 1

            # 配置 Worker
            worker.strategy_path = strategy_path
            worker.config = config
            if worker_id:
                worker.worker_id = worker_id

            # 标记为使用中
            self._in_use[worker.worker_id] = worker
            self._worker_metadata[worker.worker_id] = {
                "acquired_at": datetime.now(),
                "strategy_path": strategy_path,
                "config": config,
            }

            logger.info(f"Worker 已分配: {worker.worker_id}")
            return worker

        except Exception as e:
            logger.error(f"获取 Worker 失败: {e}")
            return None

    async def release(self, worker_id: str, restart: bool = False) -> bool:
        """
        释放 Worker 进程

        Args:
            worker_id: Worker ID
            restart: 是否重启进程（用于清理状态）

        Returns:
            是否释放成功
        """
        try:
            if worker_id not in self._in_use:
                logger.warning(f"Worker 不在使用中: {worker_id}")
                return True

            worker = self._in_use.pop(worker_id)
            self._released_count += 1

            # 停止 Worker
            await self._stop_worker(worker)

            # 如果需要，创建新进程替换
            if restart and self._running:
                new_worker = await self._create_idle_worker()
                if new_worker:
                    self._available.append(new_worker)

            # 清理元数据
            if worker_id in self._worker_metadata:
                del self._worker_metadata[worker_id]

            logger.info(f"Worker 已释放: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"释放 Worker {worker_id} 失败: {e}")
            return False

    async def _create_worker(
        self,
        strategy_path: str,
        config: Dict[str, Any],
        worker_id: Optional[str] = None,
    ) -> Optional[WorkerProcess]:
        """
        创建新的 Worker 进程

        Args:
            strategy_path: 策略文件路径
            config: 策略配置
            worker_id: 可选的 Worker ID

        Returns:
            Worker 进程或 None
        """
        try:
            import uuid

            if worker_id is None:
                worker_id = f"worker-{uuid.uuid4().hex[:8]}"

            worker = WorkerProcess(
                worker_id=worker_id,
                strategy_path=strategy_path,
                config=config,
                comm_host=self.comm_host,
                data_port=self.data_port,
                control_port=self.control_port,
                status_port=self.status_port,
            )

            return worker

        except Exception as e:
            logger.error(f"创建 Worker 失败: {e}")
            return None

    async def _create_idle_worker(self) -> Optional[WorkerProcess]:
        """
        创建空闲 Worker 进程

        Returns:
            Worker 进程或 None
        """
        try:
            import uuid

            worker_id = f"pool-worker-{uuid.uuid4().hex[:8]}"

            # 创建空配置的 Worker
            worker = WorkerProcess(
                worker_id=worker_id,
                strategy_path="",  # 空路径，稍后配置
                config={},
                comm_host=self.comm_host,
                data_port=self.data_port,
                control_port=self.control_port,
                status_port=self.status_port,
            )

            return worker

        except Exception as e:
            logger.error(f"创建空闲 Worker 失败: {e}")
            return None

    async def _stop_worker(self, worker: WorkerProcess) -> bool:
        """
        停止 Worker 进程

        Args:
            worker: Worker 进程

        Returns:
            是否停止成功
        """
        try:
            if worker.is_alive():
                worker.stop()
                worker.join(timeout=5.0)

                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=2.0)

            return True

        except Exception as e:
            logger.error(f"停止 Worker {worker.worker_id} 失败: {e}")
            return False

    def get_available_count(self) -> int:
        """
        获取可用进程数量

        Returns:
            可用进程数量
        """
        return len(self._available)

    def get_in_use_count(self) -> int:
        """
        获取使用中进程数量

        Returns:
            使用中进程数量
        """
        return len(self._in_use)

    def get_total_count(self) -> int:
        """
        获取总进程数量

        Returns:
            总进程数量
        """
        return len(self._available) + len(self._in_use)

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "available": self.get_available_count(),
            "in_use": self.get_in_use_count(),
            "total": self.get_total_count(),
            "max_size": self.config.max_size,
            "created_count": self._created_count,
            "reused_count": self._reused_count,
            "released_count": self._released_count,
        }

    async def _maintenance_loop(self):
        """
        维护循环

        定期检查和维护进程池
        """
        while self._running:
            try:
                # 检查可用进程数量，补充到最小值
                while len(self._available) < self.config.min_size:
                    worker = await self._create_idle_worker()
                    if worker:
                        self._available.append(worker)
                    else:
                        break

                # 清理已停止的进程
                self._available = [w for w in self._available if not w.is_alive()]

                # 检查使用中的进程
                dead_workers = [
                    wid for wid, w in self._in_use.items() if not w.is_alive()
                ]
                for wid in dead_workers:
                    logger.warning(f"Worker 已死亡: {wid}")
                    if wid in self._in_use:
                        del self._in_use[wid]
                    if wid in self._worker_metadata:
                        del self._worker_metadata[wid]

                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"维护循环错误: {e}")
                await asyncio.sleep(10)

    def is_worker_active(self, worker_id: str) -> bool:
        """
        检查 Worker 是否处于活动状态

        Args:
            worker_id: Worker ID

        Returns:
            是否活动
        """
        if worker_id in self._in_use:
            return self._in_use[worker_id].is_alive()
        return False

    def get_worker_info(self, worker_id: str) -> Optional[dict]:
        """
        获取 Worker 信息

        Args:
            worker_id: Worker ID

        Returns:
            Worker 信息或 None
        """
        if worker_id in self._in_use:
            worker = self._in_use[worker_id]
            metadata = self._worker_metadata.get(worker_id, {})
            return {
                "worker_id": worker_id,
                "pid": worker.pid,
                "is_alive": worker.is_alive(),
                "strategy_path": metadata.get("strategy_path"),
                "acquired_at": metadata.get("acquired_at"),
            }
        return None

    def get_all_worker_info(self) -> List[dict]:
        """
        获取所有 Worker 信息

        Returns:
            Worker 信息列表
        """
        return [
            self.get_worker_info(wid) for wid in self._in_use.keys()
        ]
