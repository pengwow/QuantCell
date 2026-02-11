"""
Worker 管理器

管理所有 Worker 进程的生命周期，提供策略启动、停止、监控等功能
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from loguru import logger

from .ipc import CommManager, DataBroker, Message, MessageType
from .state import WorkerState, WorkerStatus
from .worker_process import WorkerProcess


class WorkerManager:
    """
    Worker 管理器

    中央管理器，负责：
    - 启动和停止策略 Worker
    - 管理 Worker 生命周期
    - 处理 Worker 状态更新
    - 与 DataBroker 集成进行数据分发
    """

    def __init__(
        self,
        max_workers: int = 10,
        comm_host: str = "127.0.0.1",
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
    ):
        """
        初始化 Worker 管理器

        Args:
            max_workers: 最大 Worker 数量
            comm_host: 通信主机地址
            data_port: 数据端口
            control_port: 控制端口
            status_port: 状态端口
        """
        self.max_workers = max_workers
        self.comm_host = comm_host
        self.data_port = data_port
        self.control_port = control_port
        self.status_port = status_port

        # 通信组件
        self.comm_manager = CommManager(
            host=comm_host,
            data_port=data_port,
            control_port=control_port,
            status_port=status_port,
        )
        self.data_broker = DataBroker(self.comm_manager)

        # Worker 管理
        self._workers: Dict[str, WorkerProcess] = {}
        self._worker_status: Dict[str, WorkerStatus] = {}

        # 状态处理器
        self._status_handlers: List[Callable[[WorkerStatus], None]] = []

        # 运行状态
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """
        启动 Worker 管理器

        Returns:
            是否启动成功
        """
        try:
            # 启动通信管理器
            success = await self.comm_manager.start()
            if not success:
                logger.error("启动通信管理器失败")
                return False

            # 注册状态处理器
            self.comm_manager.register_status_handler(self._handle_status_message)

            self._running = True

            # 启动监控任务
            self._monitor_task = asyncio.create_task(self._monitor_loop())

            logger.info("Worker 管理器已启动")
            return True

        except Exception as e:
            logger.error(f"启动 Worker 管理器失败: {e}")
            await self.stop()
            return False

    async def stop(self) -> bool:
        """
        停止 Worker 管理器

        Returns:
            是否停止成功
        """
        self._running = False

        # 停止所有 Worker
        await self.stop_all_workers()

        # 取消监控任务
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # 停止通信管理器
        await self.comm_manager.stop()

        logger.info("Worker 管理器已停止")
        return True

    async def start_strategy(
        self,
        strategy_path: str,
        config: Dict[str, Any],
        worker_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        启动策略 Worker

        Args:
            strategy_path: 策略文件路径
            config: 策略配置
            worker_id: 可选的 Worker ID，如果不提供则自动生成

        Returns:
            Worker ID 或 None（如果启动失败）
        """
        try:
            # 检查 Worker 数量限制
            if len(self._workers) >= self.max_workers:
                logger.error(f"Worker 数量已达上限: {self.max_workers}")
                return None

            # 生成 Worker ID
            if worker_id is None:
                worker_id = f"worker-{uuid.uuid4().hex[:8]}"

            # 检查 Worker ID 是否已存在
            if worker_id in self._workers:
                logger.error(f"Worker ID 已存在: {worker_id}")
                return None

            # 创建 Worker 进程
            worker = WorkerProcess(
                worker_id=worker_id,
                strategy_path=strategy_path,
                config=config,
                comm_host=self.comm_host,
                data_port=self.data_port,
                control_port=self.control_port,
                status_port=self.status_port,
            )

            # 启动 Worker
            worker.start()

            # 记录 Worker
            self._workers[worker_id] = worker
            self._worker_status[worker_id] = worker.status

            # 订阅数据
            symbols = config.get("symbols", [])
            data_types = config.get("data_types", ["kline"])
            if symbols:
                self.data_broker.subscribe(worker_id, symbols, data_types)

            logger.info(f"策略 Worker 已启动: {worker_id}, 策略: {strategy_path}")
            return worker_id

        except Exception as e:
            logger.error(f"启动策略 Worker 失败: {e}")
            return None

    async def stop_worker(self, worker_id: str, timeout: float = 30.0) -> bool:
        """
        停止指定 Worker

        Args:
            worker_id: Worker ID
            timeout: 超时时间（秒）

        Returns:
            是否停止成功
        """
        try:
            if worker_id not in self._workers:
                logger.warning(f"Worker 不存在: {worker_id}")
                return True

            worker = self._workers[worker_id]

            # 发送停止命令
            await self.comm_manager.send_control(
                worker_id,
                Message.create_control(MessageType.STOP, worker_id),
            )

            # 等待 Worker 停止
            worker.join(timeout=timeout)

            # 如果 Worker 仍在运行，强制终止
            if worker.is_alive():
                logger.warning(f"Worker {worker_id} 未能在 {timeout} 秒内停止，强制终止")
                worker.terminate()
                worker.join(timeout=5.0)

            # 清理
            del self._workers[worker_id]
            if worker_id in self._worker_status:
                del self._worker_status[worker_id]

            # 取消数据订阅
            self.data_broker.unsubscribe_all(worker_id)

            logger.info(f"Worker 已停止: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"停止 Worker {worker_id} 失败: {e}")
            return False

    async def stop_all_workers(self) -> bool:
        """
        停止所有 Worker

        Returns:
            是否停止成功
        """
        worker_ids = list(self._workers.keys())
        results = []

        for worker_id in worker_ids:
            result = await self.stop_worker(worker_id)
            results.append(result)

        return all(results)

    async def pause_worker(self, worker_id: str) -> bool:
        """
        暂停指定 Worker

        Args:
            worker_id: Worker ID

        Returns:
            是否暂停成功
        """
        try:
            if worker_id not in self._workers:
                logger.warning(f"Worker 不存在: {worker_id}")
                return False

            await self.comm_manager.send_control(
                worker_id,
                Message.create_control(MessageType.PAUSE, worker_id),
            )

            logger.info(f"Worker 已暂停: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"暂停 Worker {worker_id} 失败: {e}")
            return False

    async def resume_worker(self, worker_id: str) -> bool:
        """
        恢复指定 Worker

        Args:
            worker_id: Worker ID

        Returns:
            是否恢复成功
        """
        try:
            if worker_id not in self._workers:
                logger.warning(f"Worker 不存在: {worker_id}")
                return False

            await self.comm_manager.send_control(
                worker_id,
                Message.create_control(MessageType.RESUME, worker_id),
            )

            logger.info(f"Worker 已恢复: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"恢复 Worker {worker_id} 失败: {e}")
            return False

    async def reload_worker_config(
        self, worker_id: str, config: Dict[str, Any]
    ) -> bool:
        """
        重载 Worker 配置

        Args:
            worker_id: Worker ID
            config: 新配置

        Returns:
            是否重载成功
        """
        try:
            if worker_id not in self._workers:
                logger.warning(f"Worker 不存在: {worker_id}")
                return False

            await self.comm_manager.send_control(
                worker_id,
                Message.create_control(
                    MessageType.RELOAD_CONFIG, worker_id, config
                ),
            )

            # 更新数据订阅
            symbols = config.get("symbols", [])
            data_types = config.get("data_types", ["kline"])
            if symbols:
                self.data_broker.subscribe(worker_id, symbols, data_types)

            logger.info(f"Worker 配置已重载: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"重载 Worker {worker_id} 配置失败: {e}")
            return False

    def get_worker(self, worker_id: str) -> Optional[WorkerProcess]:
        """
        获取 Worker 进程

        Args:
            worker_id: Worker ID

        Returns:
            Worker 进程或 None
        """
        return self._workers.get(worker_id)

    def get_worker_status(self, worker_id: str) -> Optional[WorkerStatus]:
        """
        获取 Worker 状态

        Args:
            worker_id: Worker ID

        Returns:
            Worker 状态或 None
        """
        return self._worker_status.get(worker_id)

    def get_all_workers(self) -> Dict[str, WorkerProcess]:
        """
        获取所有 Worker

        Returns:
            Worker 字典
        """
        return self._workers.copy()

    def get_all_status(self) -> Dict[str, WorkerStatus]:
        """
        获取所有 Worker 状态

        Returns:
            Worker 状态字典
        """
        return self._worker_status.copy()

    def get_running_workers(self) -> List[str]:
        """
        获取运行中的 Worker 列表

        Returns:
            Worker ID 列表
        """
        return [
            worker_id
            for worker_id, worker in self._workers.items()
            if worker.is_alive()
        ]

    def get_worker_count(self) -> int:
        """
        获取 Worker 数量

        Returns:
            Worker 数量
        """
        return len(self._workers)

    def get_running_count(self) -> int:
        """
        获取运行中的 Worker 数量

        Returns:
            运行中的 Worker 数量
        """
        return len(self.get_running_workers())

    def register_status_handler(self, handler: Callable[[WorkerStatus], None]):
        """
        注册状态处理器

        Args:
            handler: 处理函数，接收 WorkerStatus 参数
        """
        self._status_handlers.append(handler)

    def unregister_status_handler(self, handler: Callable[[WorkerStatus], None]):
        """
        注销状态处理器

        Args:
            handler: 处理函数
        """
        if handler in self._status_handlers:
            self._status_handlers.remove(handler)

    def _handle_status_message(self, message: Message):
        """
        处理状态消息

        Args:
            message: 状态消息
        """
        try:
            worker_id = message.worker_id
            if not worker_id:
                return

            # 更新状态
            if worker_id in self._worker_status:
                status = self._worker_status[worker_id]
                payload = message.payload

                # 更新状态字段
                if "state" in payload:
                    state_value = payload["state"]
                    try:
                        new_state = WorkerState(state_value)
                        status.update_state(new_state)
                    except ValueError:
                        pass

                # 更新心跳
                status.update_heartbeat()

                # 更新其他字段
                if "messages_processed" in payload:
                    status.messages_processed = payload["messages_processed"]
                if "orders_placed" in payload:
                    status.orders_placed = payload["orders_placed"]
                if "errors_count" in payload:
                    status.errors_count = payload["errors_count"]

            # 调用状态处理器
            if worker_id in self._worker_status:
                for handler in self._status_handlers:
                    try:
                        handler(self._worker_status[worker_id])
                    except Exception as e:
                        logger.error(f"状态处理器错误: {e}")

        except Exception as e:
            logger.error(f"处理状态消息错误: {e}")

    async def _monitor_loop(self):
        """
        监控循环

        定期检查 Worker 健康状态
        """
        while self._running:
            try:
                # 检查 Worker 健康状态
                for worker_id, worker in list(self._workers.items()):
                    if not worker.is_alive():
                        logger.warning(f"Worker {worker_id} 已退出")
                        # 清理
                        if worker_id in self._worker_status:
                            self._worker_status[worker_id].update_state(
                                WorkerState.STOPPED
                            )
                        del self._workers[worker_id]
                        self.data_broker.unsubscribe_all(worker_id)

                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(5)

    async def publish_market_data(
        self,
        symbol: str,
        data_type: str,
        data: dict,
        source: Optional[str] = None,
    ) -> bool:
        """
        发布市场数据

        Args:
            symbol: 交易对
            data_type: 数据类型
            data: 数据内容
            source: 数据来源

        Returns:
            是否发布成功
        """
        return await self.data_broker.publish(symbol, data_type, data, source)

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_workers": len(self._workers),
            "running_workers": self.get_running_count(),
            "max_workers": self.max_workers,
            "data_broker_stats": self.data_broker.get_stats(),
        }
