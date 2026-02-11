"""
Worker 进程实现

在独立进程中运行策略，通过进程间通信与主进程交互
"""

import multiprocessing
import asyncio
import signal
import os
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from loguru import logger

from .ipc import WorkerCommClient, Message, MessageType
from .state import WorkerState, WorkerStatus


class WorkerProcess(multiprocessing.Process):
    """
    策略工作进程

    在完全隔离的 Python 进程中运行单个策略，
    通过进程间通信与主进程进行交互
    """

    def __init__(
        self,
        worker_id: str,
        strategy_path: str,
        config: Dict[str, Any],
        comm_host: str = "127.0.0.1",
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
    ):
        super().__init__(daemon=True)

        self.worker_id = worker_id
        self.strategy_path = strategy_path
        self.config = config
        self.comm_host = comm_host
        self.data_port = data_port
        self.control_port = control_port
        self.status_port = status_port

        # 进程内状态
        self.status = WorkerStatus(
            worker_id=worker_id,
            strategy_path=strategy_path,
            symbols=config.get("symbols", []),
        )
        self.comm_client: Optional[WorkerCommClient] = None
        self.strategy: Optional[Any] = None

        # 运行控制
        self._shutdown_event = multiprocessing.Event()
        self._pause_event = multiprocessing.Event()

        # 统计信息
        self._messages_processed = 0
        self._orders_placed = 0

    def run(self):
        """
        进程主入口

        这是进程启动时调用的方法，设置进程环境并启动主循环
        """
        # 设置进程标题
        try:
            import setproctitle
            setproctitle.setproctitle(f"quantcell-worker:{self.worker_id}")
        except ImportError:
            pass

        # 设置进程 ID
        self.status.pid = os.getpid()

        # 设置信号处理
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._main_loop())
        except Exception as e:
            logger.error(f"Worker {self.worker_id} 主循环异常: {e}")
            self.status.record_error(str(e))
        finally:
            loop.run_until_complete(self._cleanup())
            loop.close()

    async def _main_loop(self):
        """
        主事件循环

        初始化并运行 Worker 的主要逻辑
        """
        try:
            # 1. 初始化通信连接
            await self._init_comm()

            # 2. 加载策略（在进程内部加载，确保隔离）
            await self._load_strategy()

            # 3. 订阅数据
            await self._subscribe_data()

            # 4. 启动完成，发送状态更新
            self.status.update_state(WorkerState.RUNNING)
            await self._send_status(MessageType.STATUS_UPDATE)

            logger.info(f"Worker {self.worker_id} 启动完成，开始运行")

            # 5. 主循环 - 等待关闭信号
            while not self._shutdown_event.is_set():
                if self._pause_event.is_set():
                    # 暂停状态
                    await asyncio.sleep(0.1)
                    continue

                # 发送心跳
                await self._send_heartbeat()

                # 等待一段时间
                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 主循环异常: {e}")
            self.status.update_state(WorkerState.ERROR)
            self.status.record_error(str(e))
            await self._send_status(MessageType.ERROR)
            raise

    async def _init_comm(self):
        """
        初始化通信连接
        """
        self.comm_client = WorkerCommClient(
            worker_id=self.worker_id,
            host=self.comm_host,
            data_port=self.data_port,
            control_port=self.control_port,
            status_port=self.status_port,
        )

        # 注册消息处理器
        self.comm_client.register_data_handler(self._handle_data)
        self.comm_client.register_control_handler(self._handle_control)

        # 连接到主进程
        success = await self.comm_client.connect()
        if not success:
            raise RuntimeError("无法连接到通信服务")

        self.status.update_state(WorkerState.INITIALIZED)
        logger.info(f"Worker {self.worker_id} 通信连接已建立")

    async def _load_strategy(self):
        """
        动态加载策略

        在进程内部动态加载策略模块，确保策略代码的隔离性
        """
        try:
            import importlib.util
            import sys

            # 动态加载策略模块
            module_name = f"strategy_{self.worker_id}"
            spec = importlib.util.spec_from_file_location(
                module_name, self.strategy_path
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载策略文件: {self.strategy_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 获取策略类
            strategy_class_name = self.config.get("strategy_class", "Strategy")
            strategy_class = getattr(module, strategy_class_name, None)
            if strategy_class is None:
                # 尝试查找第一个类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and attr_name not in ["StrategyBase"]:
                        strategy_class = attr
                        break

            if strategy_class is None:
                raise ImportError(f"在 {self.strategy_path} 中未找到策略类")

            # 实例化策略
            strategy_params = self.config.get("params", {})
            self.strategy = strategy_class(strategy_params)

            # 更新状态信息
            self.status.strategy_name = strategy_class.__name__

            # 调用策略初始化
            if hasattr(self.strategy, "on_init"):
                await self._call_strategy_method("on_init")

            logger.info(f"Worker {self.worker_id} 策略加载完成: {strategy_class.__name__}")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 加载策略失败: {e}")
            raise

    async def _subscribe_data(self):
        """
        订阅市场数据
        """
        symbols = self.config.get("symbols", [])
        data_types = self.config.get("data_types", ["kline"])

        if symbols and self.comm_client:
            success = self.comm_client.subscribe_symbols(symbols, data_types)
            if success:
                logger.info(f"Worker {self.worker_id} 已订阅: symbols={symbols}, types={data_types}")
            else:
                logger.warning(f"Worker {self.worker_id} 订阅数据部分失败")

    async def _handle_data(self, topic: str, message: Message):
        """
        处理市场数据

        Args:
            topic: 数据主题
            message: 数据消息
        """
        try:
            if self.status.state != WorkerState.RUNNING:
                return

            # 更新统计
            self._messages_processed += 1
            self.status.messages_processed = self._messages_processed

            # 解析数据
            symbol = message.payload.get("symbol")
            data_type = message.payload.get("data_type")
            data = message.payload.get("data")

            if not symbol or not data:
                return

            # 调用策略回调
            if data_type == "kline" and hasattr(self.strategy, "on_bar"):
                await self._call_strategy_method("on_bar", data)
            elif data_type == "tick" and hasattr(self.strategy, "on_tick"):
                await self._call_strategy_method("on_tick", data)

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 处理数据错误: {e}")
            self.status.record_error(str(e))

    async def _handle_control(self, message: Message):
        """
        处理控制命令

        Args:
            message: 控制消息
        """
        try:
            logger.info(f"Worker {self.worker_id} 收到控制命令: {message.msg_type.value}")

            if message.msg_type == MessageType.STOP:
                await self._handle_stop()
            elif message.msg_type == MessageType.PAUSE:
                await self._handle_pause()
            elif message.msg_type == MessageType.RESUME:
                await self._handle_resume()
            elif message.msg_type == MessageType.RELOAD_CONFIG:
                await self._handle_reload_config(message.payload)
            elif message.msg_type == MessageType.UPDATE_PARAMS:
                await self._handle_update_params(message.payload)
            else:
                logger.warning(f"未知的控制命令: {message.msg_type.value}")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 处理控制命令错误: {e}")
            self.status.record_error(str(e))

    async def _handle_stop(self):
        """处理停止命令"""
        logger.info(f"Worker {self.worker_id} 收到停止命令")
        self.status.update_state(WorkerState.STOPPING)
        await self._send_status(MessageType.STATUS_UPDATE)
        self._shutdown_event.set()

    async def _handle_pause(self):
        """处理暂停命令"""
        logger.info(f"Worker {self.worker_id} 收到暂停命令")
        self._pause_event.set()
        self.status.update_state(WorkerState.PAUSED)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _handle_resume(self):
        """处理恢复命令"""
        logger.info(f"Worker {self.worker_id} 收到恢复命令")
        self._pause_event.clear()
        self.status.update_state(WorkerState.RUNNING)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _handle_reload_config(self, config: Dict[str, Any]):
        """处理重载配置命令"""
        logger.info(f"Worker {self.worker_id} 收到重载配置命令")
        self.status.update_state(WorkerState.RELOADING)
        self.config.update(config)
        # 重新订阅数据
        await self._subscribe_data()
        self.status.update_state(WorkerState.RUNNING)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _handle_update_params(self, params: Dict[str, Any]):
        """处理更新参数命令"""
        logger.info(f"Worker {self.worker_id} 收到更新参数命令")
        if self.strategy and hasattr(self.strategy, "update_params"):
            await self._call_strategy_method("update_params", params)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _call_strategy_method(self, method_name: str, *args, **kwargs):
        """
        安全调用策略方法

        包装策略方法调用，捕获异常防止策略错误导致 Worker 崩溃
        """
        if not self.strategy:
            return

        try:
            method = getattr(self.strategy, method_name, None)
            if method is None:
                return

            # 检查是否是协程函数
            if asyncio.iscoroutinefunction(method):
                return await method(*args, **kwargs)
            else:
                return method(*args, **kwargs)

        except Exception as e:
            logger.error(f"策略方法 {method_name} 执行错误: {e}")
            self.status.record_error(f"{method_name}: {str(e)}")
            # 不抛出异常，防止 Worker 崩溃

    async def _send_heartbeat(self):
        """发送心跳消息"""
        self.status.update_heartbeat()
        await self._send_status(MessageType.HEARTBEAT)

    async def _send_status(self, msg_type: MessageType):
        """
        发送状态消息

        Args:
            msg_type: 消息类型
        """
        if self.comm_client:
            message = Message(
                msg_type=msg_type,
                worker_id=self.worker_id,
                payload=self.status.to_dict(),
            )
            await self.comm_client.send_status(message)

    def _handle_signal(self, signum, frame):
        """
        处理系统信号

        Args:
            signum: 信号编号
            frame: 当前栈帧
        """
        logger.info(f"Worker {self.worker_id} 收到信号 {signum}")
        self._shutdown_event.set()

    async def _cleanup(self):
        """
        清理资源
        """
        logger.info(f"Worker {self.worker_id} 开始清理资源")

        # 调用策略清理方法
        if self.strategy and hasattr(self.strategy, "on_stop"):
            try:
                await self._call_strategy_method("on_stop")
            except Exception as e:
                logger.error(f"策略清理错误: {e}")

        # 断开通信连接
        if self.comm_client:
            await self.comm_client.disconnect()

        # 更新状态
        self.status.update_state(WorkerState.STOPPED)

        logger.info(f"Worker {self.worker_id} 资源清理完成")

    def stop(self):
        """
        请求停止 Worker（在主进程中调用）
        """
        self._shutdown_event.set()

    def pause(self):
        """
        请求暂停 Worker（在主进程中调用）
        """
        self._pause_event.set()

    def resume(self):
        """
        请求恢复 Worker（在主进程中调用）
        """
        self._pause_event.clear()

    def is_running(self) -> bool:
        """
        检查 Worker 是否正在运行

        Returns:
            是否正在运行
        """
        return self.is_alive() and not self._shutdown_event.is_set()

    def is_paused(self) -> bool:
        """
        检查 Worker 是否已暂停

        Returns:
            是否已暂停
        """
        return self._pause_event.is_set()
