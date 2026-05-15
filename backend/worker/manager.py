"""
Worker 管理器（事件驱动版本）

管理所有 Worker 进程的生命周期，响应状态变更事件而不是主动管理状态
- 响应 state_manager 的状态变更事件
- 执行具体的进程创建、停止、清理操作
- 提供健康检查和监控功能
"""

import asyncio
import os
import signal
import uuid
from typing import Dict, List, Optional, Any, Callable
from utils.logger import get_logger, LogType
from core.port_manager import port_manager
from utils.deprecation import deprecated_compat

logger = get_logger(__name__, LogType.APPLICATION)

from .state import WorkerState, WorkerStatus
from .worker_process import WorkerProcess
from .worker_state import worker_state_manager

# IPC 组件（可选导入，如果不可用则禁用 IPC 功能）
_ipc_available = False
CommManager = None
DataBroker = None
Message = None
MessageType = None
try:
    from .ipc import CommManager, DataBroker, Message, MessageType
    _ipc_available = True
    logger.info("IPC 模块加载成功")
except ImportError as e:
    logger.warning(f"IPC 模块不可用，将禁用 IPC 功能: {e}")


class WorkerManager:
    """
    Worker 管理器（事件驱动）

    从"主动管理者"转变为"被动执行者"，核心职责：
    - 监听并响应 state_manager 的状态变更事件
    - 执行进程级别的操作（创建、停止、清理）
    - 跟踪运行中的进程对象（不存储状态信息）
    - 提供健康检查和监控

    状态管理的唯一权威是 worker_state_manager
    """

    def __init__(
        self,
        max_workers: int = 10,
        comm_host: str = "127.0.0.1",
        data_port: Optional[int] = None,
        control_port: Optional[int] = None,
        status_port: Optional[int] = None,
    ):
        """
        初始化 Worker 管理器（事件驱动版本）

        Args:
            max_workers: 最大 Worker 数量
            comm_host: 通信主机地址
            data_port: 数据端口（可选，默认从 PortManager 获取）
            control_port: 控制端口（可选，默认从 PortManager 获取）
            status_port: 状态端口（可选，默认从 PortManager 获取）
        """
        self.max_workers = max_workers
        self.comm_host = comm_host
        self.data_port = data_port if data_port is not None else port_manager.get_port("zmq_data")
        self.control_port = control_port if control_port is not None else port_manager.get_port("zmq_control")
        self.status_port = status_port if status_port is not None else port_manager.get_port("zmq_status")

        logger.info(f"初始化 Worker 管理器 [事件驱动] | data_port={self.data_port} | control_port={self.control_port} | status_port={self.status_port}")

        # 通信组件（仅当 IPC 可用时初始化）
        self.comm_manager = None
        self.data_broker = None
        if _ipc_available:
            try:
                self.comm_manager = CommManager(
                    host=comm_host,
                    data_port=data_port,
                    control_port=control_port,
                    status_port=status_port,
                )
                self.data_broker = DataBroker(self.comm_manager)
                logger.info("IPC 通信组件初始化成功")
            except Exception as e:
                logger.error(f"IPC 通信组件初始化失败: {e}")
                self.comm_manager = None
                self.data_broker = None
        else:
            logger.info("IPC 不可用，跳过通信组件初始化")

        # 进程跟踪字典（仅存储进程对象，不存储状态信息）
        # 状态信息的唯一来源是 worker_state_manager
        self._workers: Dict[str, WorkerProcess] = {}

        # 向后兼容：保留 _worker_status 字典但标记为 deprecated
        # 新代码应使用 worker_state_manager.get_state() 获取状态
        self._worker_status: Dict[str, WorkerStatus] = {}

        # 状态处理器（向后兼容）
        self._status_handlers: List[Callable[[WorkerStatus], None]] = []

        # Worker 退出回调（向后兼容）
        self._worker_exit_callbacks: List[Callable[[str, WorkerStatus], None]] = []

        # 运行状态
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None

        # 注册为 state_manager 的事件监听者
        # 这是核心改动：manager 不再主动管理状态，而是响应状态变更事件
        worker_state_manager.register_handler("state_changed", self._on_state_changed)
        logger.info("已注册为 state_changed 事件的监听者")

    async def start(self) -> bool:
        """
        启动 Worker 管理器

        Returns:
            是否启动成功
        """
        try:
            # 仅当 IPC 可用时启动通信管理器
            if self.comm_manager:
                success = await self.comm_manager.start()
                if not success:
                    logger.error("启动通信管理器失败")
                    return False

                self.comm_manager.register_status_handler(self._handle_status_message)
            else:
                logger.info("IPC 不可用，跳过通信管理器启动")

            self._running = True

            # 启动监控任务（检测进程退出等）
            self._monitor_task = asyncio.create_task(self._monitor_loop())

            # 启动健康检查任务（定期检查进程健康状态）
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            logger.info("Worker 管理器已启动 [事件驱动模式]")
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

        await self._force_stop_all_workers()

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            except RuntimeError as e:
                if 'different loop' not in str(e):
                    raise

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            except RuntimeError as e:
                if 'different loop' not in str(e):
                    raise

        try:
            # 仅当 IPC 可用时停止通信管理器
            if self.comm_manager:
                await self.comm_manager.stop()
        except (asyncio.CancelledError, RuntimeError):
            pass

        logger.info("Worker 管理器已停止")
        return True

    async def _send_control_safe(self, worker_id: str, message_type: Any, *args) -> bool:
        """
        安全地发送控制消息（IPC 可选）

        如果 IPC 不可用或发送失败，返回 False 而不是抛出异常

        Args:
            worker_id: Worker ID
            message_type: 消息类型
            *args: 额外参数

        Returns:
            是否发送成功
        """
        if not self.comm_manager or not _ipc_available:
            logger.debug(f"IPC 不可用，跳过发送控制消息给 {worker_id}")
            return False

        try:
            await self.comm_manager.send_control(
                worker_id,
                Message.create_control(message_type, worker_id, *args),
            )
            return True
        except Exception as e:
            logger.warning(f"发送控制消息失败 (worker_id={worker_id}): {e}")
            return False

    # =========================================================================
    # 核心事件处理器 - 响应 state_manager 的状态变更事件
    # =========================================================================

    async def _on_state_changed(self, event_data: dict):
        """
        响应 Worker 状态变更事件（核心事件处理器）

        当 worker_state_manager 执行状态转换后会触发此方法，
        manager 根据新状态执行相应的进程级操作

        Args:
            event_data: {
                "worker_id": int,
                "old_status": str,
                "new_status": str,
                "timestamp": str,
            }
        """
        worker_id = event_data["worker_id"]
        new_status = event_data["new_status"]
        old_status = event_data.get("old_status", "unknown")

        logger.info(
            f"[事件驱动] 收到状态变更事件 | "
            f"worker_id={worker_id} | {old_status} -> {new_status}"
        )

        try:
            if new_status == "starting":
                await self._handle_start_event(worker_id)
            elif new_status == "stopping":
                await self._handle_stop_event(worker_id)
            elif new_status in ("stopped", "error"):
                await self._handle_cleanup_event(worker_id, new_status)
            else:
                logger.debug(f"[事件驱动] 状态 {new_status} 无需特殊处理")
        except Exception as e:
            logger.error(
                f"[事件驱动] 处理状态变更事件失败 | "
                f"worker_id={worker_id} | status={new_status} | error={e}",
                exc_info=True
            )

    async def _handle_start_event(self, worker_id: int):
        """
        处理启动事件

        从数据库读取 Worker 配置，创建并启动 WorkerProcess 子进程

        Args:
            worker_id: Worker ID（数据库主键）
        """
        logger.info(f"[启动事件] 开始处理 Worker {worker_id} 启动")

        try:
            from collector.db.database import SessionLocal
            from worker.crud import get_worker_by_id

            db = SessionLocal()
            try:
                worker_record = get_worker_by_id(db, worker_id)
                if not worker_record:
                    logger.error(f"[启动事件] Worker {worker_id} 在数据库中不存在")
                    await worker_state_manager.transition(
                        worker_id, "error",
                        error_message="Worker record not found in database"
                    )
                    return

                strategy_path = worker_record.strategy_path
                config = worker_record.config or {}
                process_id = f"worker-{worker_id}"

                if len(self._workers) >= self.max_workers:
                    logger.error(f"[启动事件] Worker 数量已达上限: {self.max_workers}")
                    await worker_state_manager.transition(
                        worker_id, "error",
                        error_message=f"Max workers limit reached: {self.max_workers}"
                    )
                    return

                if process_id in self._workers:
                    logger.warning(f"[启动事件] Worker 进程已存在: {process_id}")
                    return

                worker = WorkerProcess(
                    worker_id=process_id,
                    strategy_path=strategy_path,
                    config=config,
                    comm_host=self.comm_host,
                    data_port=self.data_port,
                    control_port=self.control_port,
                    status_port=self.status_port,
                )

                worker.start()

                self._workers[process_id] = worker

                symbols = config.get("symbols", [])
                data_types = config.get("data_types", ["kline"])
                if symbols:
                    self.data_broker.subscribe(process_id, symbols, data_types)

                await worker_state_manager.transition(
                    worker_id, "running",
                    pid=worker.pid
                )

                logger.info(
                    f"[启动事件] Worker {worker_id} ({process_id}) 已启动 | "
                    f"pid={worker.pid} | strategy={strategy_path}"
                )

            finally:
                db.close()

        except Exception as e:
            logger.error(f"[启动事件] Worker {worker_id} 启动失败: {e}", exc_info=True)
            try:
                await worker_state_manager.transition(
                    worker_id, "error",
                    error_message=str(e)
                )
            except Exception as transition_error:
                logger.error(f"[启动事件] 更新状态为 error 失败: {transition_error}")

    async def _handle_stop_event(self, worker_id: int):
        """
        处理停止事件

        向 Worker 进程发送 STOP 控制信号或 SIGTERM

        Args:
            worker_id: Worker ID
        """
        logger.info(f"[停止事件] 开始处理 Worker {worker_id} 停止")

        try:
            process_id = f"worker-{worker_id}"
            worker = self._workers.get(process_id)

            if not worker:
                logger.warning(f"[停止事件] Worker {worker_id} 进程不存在，可能已经退出")
                return

            await self.comm_manager.send_control(
                process_id,
                Message.create_control(MessageType.STOP, process_id),
            )

            asyncio.create_task(self._wait_worker_stop(process_id, worker, timeout=30.0))

            logger.info(f"[停止事件] Worker {worker_id} 停止命令已发送")

        except Exception as e:
            logger.error(f"[停止事件] Worker {worker_id} 停止失败: {e}", exc_info=True)

    async def _handle_cleanup_event(self, worker_id: int, status: str):
        """
        处理清理事件（stopped/error 状态后的清理工作）

        清理进程对象、资源、取消数据订阅等

        Args:
            worker_id: Worker ID
            status: 最终状态（stopped 或 error）
        """
        logger.info(f"[清理事件] 开始处理 Worker {worker_id} 清理 | status={status}")

        try:
            process_id = f"worker-{worker_id}"

            if process_id in self._workers:
                del self._workers[process_id]
                logger.debug(f"[清理事件] 已从 _workers 移除: {process_id}")

            if process_id in self._worker_status:
                del self._worker_status[process_id]

            self.data_broker.unsubscribe_all(process_id)

            for callback in self._worker_exit_callbacks:
                try:
                    callback(process_id, WorkerStatus(worker_id=process_id))
                except Exception as e:
                    logger.error(f"[清理事件] 退出回调执行失败: {e}")

            logger.info(f"[清理事件] Worker {worker_id} 清理完成 | final_status={status}")

        except Exception as e:
            logger.error(f"[清理事件] Worker {worker_id} 清理失败: {e}", exc_info=True)

    # =========================================================================
    # 健康检查机制
    # =========================================================================

    async def _health_check_loop(self):
        """
        定期健康检查循环

        每 30 秒检查一次所有 Worker 进程的健康状态：
        - 检测僵尸进程
        - 检测进程意外退出
        - 自动修正 state_manager 状态
        """
        logger.info("[健康检查] 循环已启动，间隔 30 秒")

        while self._running:
            try:
                await asyncio.sleep(30)
                await self._check_all_workers_health()
            except asyncio.CancelledError:
                logger.info("[健康检查] 循环已取消")
                break
            except Exception as e:
                logger.error(f"[健康检查] 循环异常: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _check_all_workers_health(self):
        """
        检查所有 Worker 进程的健康状态

        检查项：
        1. 进程是否存在（os.kill(pid, 0)）
        2. 如果进程不存在但 state_manager 显示为 running → 自动修正为 error/stopped
        3. 检测僵尸进程并清理
        """
        logger.debug("[健康检查] 开始检查所有 Worker 进程")

        for process_id, worker in list(self._workers.items()):
            try:
                pid = worker.pid
                if pid is None:
                    continue

                is_alive = self._is_process_alive(pid)

                if not is_alive:
                    logger.warning(
                        f"[健康检查] Worker {process_id} (pid={pid}) 进程已不存在"
                    )

                    worker_db_id = self._extract_worker_id(process_id)
                    if worker_db_id:
                        current_state = await worker_state_manager.get_state(worker_db_id)
                        if current_state and current_state.status == "running":
                            logger.warning(
                                f"[健康检查] 自动修正 Worker {worker_db_id} 状态: running -> error"
                            )
                            await worker_state_manager.transition(
                                worker_db_id, "error",
                                error_message="Process died unexpectedly (health check)"
                            )

                    exit_code = worker.exitcode
                    logger.info(
                        f"[健康检查] Worker {process_id} 退出码: {exit_code}"
                    )

            except Exception as e:
                logger.error(
                    f"[健康检查] 检查 Worker {process_id} 失败: {e}",
                    exc_info=True
                )

    def _is_process_alive(self, pid: int) -> bool:
        """
        检查进程是否存活

        使用 os.kill(pid, 0) 发送空信号来检测进程是否存在

        Args:
            pid: 进程 ID

        Returns:
            进程是否存活
        """
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception as e:
            logger.warning(f"检查进程存活状态异常 (pid={pid}): {e}")
            return False

    def _extract_worker_id(self, process_id: str) -> Optional[int]:
        """
        从 process_id 中提取 worker 数据库 ID

        Args:
            process_id: 进程 ID（格式：worker-{db_id} 或 trading-{db_id}）

        Returns:
            数据库 ID 或 None
        """
        try:
            if process_id.startswith("worker-"):
                return int(process_id.replace("worker-", ""))
            elif process_id.startswith("trading-"):
                return int(process_id.replace("trading-", ""))
            return None
        except (ValueError, AttributeError):
            return None

    # =========================================================================
    # 改进的监控循环
    # =========================================================================

    async def _monitor_loop(self):
        """
        监控循环（改进版）

        检测 Worker 进程退出，自动更新 state_manager 状态
        与健康检查互补：监控循环关注进程退出事件，健康检查关注进程存活状态
        """
        while self._running:
            try:
                for process_id, worker in list(self._workers.items()):
                    if not worker.is_alive():
                        logger.warning(f"[监控] Worker {process_id} 已退出")

                        worker_db_id = self._extract_worker_id(process_id)
                        if worker_db_id:
                            exit_code = worker.exitcode
                            final_status = "error" if exit_code != 0 else "stopped"

                            logger.info(
                                f"[监控] Worker {process_id} (db_id={worker_db_id}) 退出 | "
                                f"exit_code={exit_code} | final_status={final_status}"
                            )

                            await worker_state_manager.transition(
                                worker_db_id, final_status,
                                error_message=f"Process exited with code: {exit_code}" if exit_code != 0 else None
                            )

                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[监控] 循环错误: {e}", exc_info=True)
                await asyncio.sleep(5)

    # =========================================================================
    # 向后兼容的公共方法（内部实现改为调用新的事件处理逻辑）
    # =========================================================================

    @deprecated_compat(new_api="worker_state_manager.transition(worker_id, 'starting')")
    async def start_strategy(
        self,
        strategy_path: str,
        config: Dict[str, Any],
        worker_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        启动策略 Worker（向后兼容接口）

        .. deprecated:: 2.1
            新代码应优先使用 worker_state_manager.transition() 触发启动流程

        Args:
            strategy_path: 策略文件路径
            config: 策略配置
            worker_id: 可选的 Worker ID，如果不提供则自动生成

        Returns:
            Worker ID 或 None（如果启动失败）
        """
        try:
            if len(self._workers) >= self.max_workers:
                logger.error(f"Worker 数量已达上限: {self.max_workers}")
                return None

            if worker_id is None:
                worker_id = f"worker-{uuid.uuid4().hex[:8]}"

            if worker_id in self._workers:
                logger.error(f"Worker ID 已存在: {worker_id}")
                return None

            worker = WorkerProcess(
                worker_id=worker_id,
                strategy_path=strategy_path,
                config=config,
                comm_host=self.comm_host,
                data_port=self.data_port,
                control_port=self.control_port,
                status_port=self.status_port,
            )

            worker.start()

            self._workers[worker_id] = worker
            self._worker_status[worker_id] = worker.status

            symbols = config.get("symbols", [])
            data_types = config.get("data_types", ["kline"])
            if symbols:
                self.data_broker.subscribe(worker_id, symbols, data_types)

            logger.info(f"策略 Worker 已启动: {worker_id}, 策略: {strategy_path}")
            return worker_id

        except Exception as e:
            logger.error(f"启动策略 Worker 失败: {e}")
            return None

    @deprecated_compat(new_api="worker_state_manager.transition(worker_id, 'stopping')")
    async def stop_worker(self, worker_id: str, timeout: float = 30.0) -> bool:
        """
        停止指定 Worker（向后兼容接口）

        .. deprecated:: 2.1
            使用 `worker_state_manager.transition(worker_id, 'stopping')` 替代

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

            await self.comm_manager.send_control(
                worker_id,
                Message.create_control(MessageType.STOP, worker_id),
            )

            import asyncio
            asyncio.create_task(self._wait_worker_stop(worker_id, worker, timeout))

            logger.info(f"Worker {worker_id} 停止命令已发送")
            return True

        except Exception as e:
            logger.error(f"停止 Worker {worker_id} 失败: {e}")
            return False

    async def _wait_worker_stop(self, worker_id: str, worker, timeout: float):
        """后台等待 Worker 停止并清理资源"""
        logger.info(f"[Manager] 开始等待 Worker {worker_id} 停止，超时时间: {timeout}秒")
        try:
            worker.join(timeout=timeout)

            is_alive = worker.is_alive()
            logger.info(f"[Manager] Worker {worker_id} join() 返回，is_alive={is_alive}")

            if is_alive:
                logger.warning(f"[Manager] Worker {worker_id} 未能在 {timeout} 秒内停止，准备强制终止")
                worker.terminate()
                logger.info(f"[Manager] Worker {worker_id} terminate() 已调用，等待 5 秒...")
                worker.join(timeout=5.0)
                logger.info(f"[Manager] Worker {worker_id} 强制终止后 is_alive={worker.is_alive()}")
            else:
                logger.info(f"[Manager] Worker {worker_id} 已正常停止")

            logger.info(f"[Manager] 开始清理 Worker {worker_id} 资源...")
            if worker_id in self._workers:
                del self._workers[worker_id]
                logger.info(f"[Manager] Worker {worker_id} 已从 _workers 中移除")
            if worker_id in self._worker_status:
                del self._worker_status[worker_id]
                logger.info(f"[Manager] Worker {worker_id} 已从 _worker_status 中移除")

            logger.info(f"[Manager] 取消 Worker {worker_id} 的数据订阅...")
            self.data_broker.unsubscribe_all(worker_id)

            logger.info(f"[Manager] Worker {worker_id} 停止流程完成")
        except Exception as e:
            logger.error(f"[Manager] 等待 Worker {worker_id} 停止时出错: {e}", exc_info=True)

    async def _force_stop_all_workers(self):
        """强制停止所有 Worker（在 shutdown 时调用）"""
        worker_ids = list(self._workers.keys())
        if not worker_ids:
            return

        logger.info(f"正在停止 {len(worker_ids)} 个 Worker 进程...")
        for worker_id in worker_ids:
            try:
                if worker_id not in self._workers:
                    continue
                worker = self._workers[worker_id]

                await self.comm_manager.send_control(
                    worker_id,
                    Message.create_control(MessageType.STOP, worker_id),
                )

                await asyncio.to_thread(worker.join, timeout=10.0)

                worker_status = self._worker_status.get(worker_id)
                if worker_status is None:
                    worker_status = WorkerStatus(worker_id=worker_id)
                    worker_status.update_state(WorkerState.STOPPED)

                if worker.is_alive():
                    logger.warning(f"Worker {worker_id} 未在 10 秒内停止，强制终止")
                    worker.terminate()
                    await asyncio.to_thread(worker.join, timeout=3.0)

                worker_status.update_state(WorkerState.STOPPED)
                for callback in self._worker_exit_callbacks:
                    try:
                        callback(worker_id, worker_status)
                    except Exception as e:
                        logger.error(f"Worker {worker_id} 退出回调执行失败: {e}")

                if worker_id in self._workers:
                    del self._workers[worker_id]
                if worker_id in self._worker_status:
                    del self._worker_status[worker_id]
                self.data_broker.unsubscribe_all(worker_id)

                logger.info(f"Worker {worker_id} 已停止，数据库状态已更新")
            except Exception as e:
                logger.error(f"强制停止 Worker {worker_id} 失败: {e}")
        logger.info("所有 Worker 进程已停止")

    @deprecated_compat(new_api="使用事件监听机制")
    def register_worker_exit_callback(
        self, callback: Callable[[str, WorkerStatus], None]
    ) -> None:
        """
        注册 Worker 退出回调函数（向后兼容）

        .. deprecated:: 2.1
            使用事件监听机制替代
        """
        self._worker_exit_callbacks.append(callback)
        logger.debug(f"注册 Worker 退出回调: {callback.__name__}")

    @deprecated_compat(new_api="使用事件监听机制")
    def unregister_worker_exit_callback(
        self, callback: Callable[[str, WorkerStatus], None]
    ) -> None:
        """
        注销 Worker 退出回调函数（向后兼容）

        .. deprecated:: 2.1
            使用事件监听机制替代
        """
        if callback in self._worker_exit_callbacks:
            self._worker_exit_callbacks.remove(callback)
            logger.debug(f"注销 Worker 退出回调: {callback.__name__}")

    def get_worker_pid(self, worker_id: str) -> Optional[int]:
        """获取 Worker 进程的 PID"""
        if worker_id in self._workers:
            worker = self._workers[worker_id]
            return worker.pid
        return None

    async def stop_all_workers(self) -> bool:
        """停止所有 Worker"""
        worker_ids = list(self._workers.keys())
        results = []

        for worker_id in worker_ids:
            result = await self.stop_worker(worker_id)
            results.append(result)

        return all(results)

    async def pause_worker(self, worker_id: str) -> bool:
        """暂停指定 Worker"""
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
        """恢复指定 Worker"""
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
        """重载 Worker 配置"""
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
        """获取 Worker 进程"""
        return self._workers.get(worker_id)

    @deprecated_compat(new_api="worker_state_manager.get_state(worker_id)")
    def get_worker_status(self, worker_id: str) -> Optional[WorkerStatus]:
        """
        获取 Worker 状态（向后兼容）

        .. deprecated:: 2.1
            使用 `worker_state_manager.get_state(worker_id)` 替代

        优先从 worker_state_manager 获取最新状态
        """
        worker_db_id = self._extract_worker_id(worker_id)
        if worker_db_id:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    state = asyncio.ensure_future(worker_state_manager.get_state(worker_db_id))
                    if state.done() and state.result():
                        return WorkerStatus(
                            worker_id=worker_id,
                            state=WorkerState(state.result().status.upper())
                        )
            except Exception:
                pass

        return self._worker_status.get(worker_id)

    def get_all_workers(self) -> Dict[str, WorkerProcess]:
        """获取所有 Worker"""
        return self._workers.copy()

    @deprecated_compat(new_api="worker_state_manager.get_all_states()")
    def get_all_status(self) -> Dict[str, WorkerStatus]:
        """
        获取所有 Worker 状态（向后兼容）

        .. deprecated:: 2.1
            使用 `worker_state_manager.get_all_states()` 替代
        """
        return self._worker_status.copy()

    def get_running_workers(self) -> List[str]:
        """获取运行中的 Worker 列表"""
        return [
            worker_id
            for worker_id, worker in self._workers.items()
            if worker.is_alive()
        ]

    def get_worker_count(self) -> int:
        """获取 Worker 数量"""
        return len(self._workers)

    def get_running_count(self) -> int:
        """获取运行中的 Worker 数量"""
        return len(self.get_running_workers())

    @deprecated_compat(new_api="使用事件订阅机制")
    def register_status_handler(self, handler: Callable[[WorkerStatus], None]):
        """
        注册状态处理器（向后兼容）

        .. deprecated:: 2.1
            使用事件订阅机制替代
        """
        self._status_handlers.append(handler)

    @deprecated_compat(new_api="使用事件订阅机制")
    def unregister_status_handler(self, handler: Callable[[WorkerStatus], None]):
        """
        注销状态处理器（向后兼容）

        .. deprecated:: 2.1
            使用事件订阅机制替代
        """
        if handler in self._status_handlers:
            self._status_handlers.remove(handler)

    def _handle_status_message(self, message: Message):
        """
        处理状态消息（IPC 通信层的状态更新）

        注意：此方法处理的是 IPC 层面的心跳和统计消息，
        不是 state_manager 的状态转换事件
        """
        try:
            worker_id = message.worker_id
            if not worker_id:
                logger.warning("[_handle_status_message] worker_id 为空，忽略消息")
                return

            if message.msg_type != MessageType.LOG:
                logger.debug(f"[_handle_status_message] 收到状态消息: worker_id={worker_id}, msg_type={message.msg_type}")

            if worker_id in self._worker_status:
                status = self._worker_status[worker_id]
                payload = message.payload

                if "state" in payload:
                    state_value = payload["state"]
                    try:
                        new_state = WorkerState(state_value)
                        old_state = status.state
                        if old_state != new_state:
                            update_success = status.update_state(new_state)
                            if update_success:
                                logger.info(f"[_handle_status_message] Worker {worker_id} 状态更新: {old_state.name} -> {new_state.name}")
                            else:
                                logger.warning(f"[_handle_status_message] Worker {worker_id} 状态转换被拒绝: {old_state.name} -> {new_state.name}")
                    except ValueError as e:
                        logger.error(f"[_handle_status_message] 状态值无效: {state_value}, error: {e}")

                status.update_heartbeat()

                if "messages_processed" in payload:
                    status.messages_processed = payload["messages_processed"]
                if "orders_placed" in payload:
                    status.orders_placed = payload["orders_placed"]
                if "errors_count" in payload:
                    status.errors_count = payload["errors_count"]
            else:
                logger.debug(f"[_handle_status_message] Worker {worker_id} 不在 _worker_status 中（可能由 WorkerSystem/事件驱动管理），已知 workers: {list(self._worker_status.keys())}")

            if worker_id in self._worker_status:
                for handler in self._status_handlers:
                    try:
                        handler(self._worker_status[worker_id])
                    except Exception as e:
                        logger.error(f"状态处理器错误: {e}")

        except Exception as e:
            logger.error(f"处理状态消息错误: {e}")

    async def publish_market_data(
        self,
        symbol: str,
        data_type: str,
        data: dict,
        source: Optional[str] = None,
    ) -> bool:
        """发布市场数据"""
        return await self.data_broker.publish(symbol, data_type, data, source)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_workers": len(self._workers),
            "running_workers": self.get_running_count(),
            "max_workers": self.max_workers,
            "data_broker_stats": self.data_broker.get_stats(),
            "mode": "event_driven",
            "health_check_active": self._health_check_task is not None and not self._health_check_task.done(),
        }


# =============================================================================
# TradingNode Worker 管理器（支持 Nautilus Trader）
# =============================================================================

class TradingNodeWorkerManager(WorkerManager):
    """
    TradingNode Worker 管理器（事件驱动版本）

    继承自事件驱动的 WorkerManager，提供 TradingNode 特定功能
    """

    def __init__(
        self,
        max_workers: int = 10,
        comm_host: str = "127.0.0.1",
        data_port: Optional[int] = None,
        control_port: Optional[int] = None,
        status_port: Optional[int] = None,
        enable_monitoring: bool = True,
    ):
        """
        初始化 TradingNode Worker 管理器

        Args:
            max_workers: 最大 Worker 数量
            comm_host: 通信主机地址
            data_port: 数据端口（可选，默认从 PortManager 获取）
            control_port: 控制端口（可选，默认从 PortManager 获取）
            status_port: 状态端口（可选，默认从 PortManager 获取）
            enable_monitoring: 是否启用监控
        """
        super().__init__(
            max_workers=max_workers,
            comm_host=comm_host,
            data_port=data_port,
            control_port=control_port,
            status_port=status_port,
        )

        self.trading_config: Dict[str, Any] = {}
        self.exchange_adapters: Dict[str, Any] = {}
        self.enable_monitoring = enable_monitoring
        self._trading_workers: Dict[str, Any] = {}

    @deprecated_compat(new_api="start_strategy_worker()")
    async def start_trading_worker(
        self,
        strategy_path: str,
        config: Dict[str, Any],
        worker_id: Optional[str] = None,
        exchange_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        启动 TradingNode Worker（向后兼容接口）

        .. deprecated:: 2.1
            使用 `start_strategy_worker()` 替代

        Args:
            strategy_path: 策略文件路径
            config: 策略配置
            worker_id: 可选的 Worker ID
            exchange_config: 交易所配置

        Returns:
            Worker ID 或 None（如果启动失败）
        """
        try:
            if len(self._workers) >= self.max_workers:
                logger.error(f"Worker 数量已达上限: {self.max_workers}")
                return None

            if worker_id is None:
                worker_id = f"trading-{uuid.uuid4().hex[:8]}"

            if worker_id in self._workers:
                logger.error(f"Worker ID 已存在: {worker_id}")
                return None

            merged_config = self._merge_config(config, exchange_config)

            from .worker_process import TradingNodeWorkerProcess

            worker = TradingNodeWorkerProcess(
                worker_id=worker_id,
                strategy_path=strategy_path,
                config=merged_config,
                comm_host=self.comm_host,
                data_port=self.data_port,
                control_port=self.control_port,
                status_port=self.status_port,
            )

            worker.start()

            self._workers[worker_id] = worker
            self._trading_workers[worker_id] = worker
            self._worker_status[worker_id] = worker.status

            symbols = merged_config.get("symbols", [])
            data_types = merged_config.get("data_types", ["kline"])
            if symbols:
                self.data_broker.subscribe(worker_id, symbols, data_types)

            logger.info(f"TradingNode Worker 已启动: {worker_id}, 策略: {strategy_path}")
            return worker_id

        except Exception as e:
            logger.error(f"启动 TradingNode Worker 失败: {e}")
            return None

    @deprecated_compat(new_api="stop_worker()")
    async def stop_trading_worker(self, worker_id: str, timeout: float = 30.0) -> bool:
        """
        停止 TradingNode Worker（向后兼容接口）

        .. deprecated:: 2.1
            使用 `stop_worker()` 替代

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

            await self.comm_manager.send_control(
                worker_id,
                Message.create_control(MessageType.STOP, worker_id),
            )

            worker.join(timeout=timeout)

            if worker.is_alive():
                logger.warning(f"Worker {worker_id} 未能在 {timeout} 秒内停止，强制终止")
                worker.terminate()
                worker.join(timeout=5.0)

            del self._workers[worker_id]
            if worker_id in self._trading_workers:
                del self._trading_workers[worker_id]
            if worker_id in self._worker_status:
                del self._worker_status[worker_id]

            self.data_broker.unsubscribe_all(worker_id)

            logger.info(f"TradingNode Worker 已停止: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"停止 TradingNode Worker {worker_id} 失败: {e}")
            return False

    def get_trading_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """获取 TradingNode Worker 状态"""
        if worker_id not in self._trading_workers:
            return None

        worker = self._trading_workers[worker_id]
        base_status = self._worker_status.get(worker_id)

        status = {
            "worker_id": worker_id,
            "base_status": base_status.to_dict() if base_status else None,
            "process_alive": worker.is_alive(),
        }

        if hasattr(worker, 'trading_node') and worker.trading_node:
            trading_node_status = self._get_trading_node_status(worker.trading_node)
            status["trading_node"] = trading_node_status

        if hasattr(worker, 'trading_strategy') and worker.trading_strategy:
            status["strategy"] = {
                "name": type(worker.trading_strategy).__name__,
                "has_trading_node": worker.trading_node is not None,
            }

        return status

    def get_all_trading_workers(self) -> Dict[str, Any]:
        """获取所有 TradingNode Worker"""
        return self._trading_workers.copy()

    def get_trading_worker_count(self) -> int:
        """获取 TradingNode Worker 数量"""
        return len(self._trading_workers)

    def set_trading_config(self, config: Dict[str, Any]) -> None:
        """设置 TradingNode 全局配置"""
        self.trading_config.update(config)
        logger.info("TradingNode 全局配置已更新")

    def register_exchange_adapter(self, exchange_name: str, adapter_config: Dict[str, Any]) -> None:
        """注册交易所适配器"""
        self.exchange_adapters[exchange_name] = adapter_config
        logger.info(f"交易所适配器已注册: {exchange_name}")

    def _merge_config(
        self,
        config: Dict[str, Any],
        exchange_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """合并配置"""
        merged = config.copy()

        if self.trading_config:
            merged["trading"] = {**self.trading_config, **merged.get("trading", {})}

        if exchange_config:
            merged["exchange"] = exchange_config

            if "trading" not in merged:
                merged["trading"] = {}

            if "data_clients" not in merged["trading"]:
                merged["trading"]["data_clients"] = {}

            if "exec_clients" not in merged["trading"]:
                merged["trading"]["exec_clients"] = {}

            exchange_name = exchange_config.get("name", "binance")
            merged["trading"]["data_clients"][exchange_name] = exchange_config
            merged["trading"]["exec_clients"][exchange_name] = exchange_config

        return merged

    def _get_trading_node_status(self, trading_node) -> Dict[str, Any]:
        """获取 TradingNode 状态"""
        status = {
            "initialized": trading_node is not None,
        }

        try:
            if hasattr(trading_node, 'is_running'):
                status["is_running"] = trading_node.is_running

            if hasattr(trading_node, 'strategies'):
                status["strategy_count"] = len(trading_node.strategies)

            if hasattr(trading_node, 'portfolio'):
                portfolio = trading_node.portfolio
                status["portfolio"] = {
                    "positions_count": len(portfolio.positions) if hasattr(portfolio, 'positions') else 0,
                }

            if hasattr(trading_node, 'clock'):
                clock = trading_node.clock
                if hasattr(clock, 'timestamp_ns'):
                    status["clock_timestamp_ns"] = clock.timestamp_ns

        except Exception as e:
            logger.debug(f"获取 TradingNode 状态失败: {e}")

        return status
