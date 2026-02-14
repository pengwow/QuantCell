"""
通信管理器

管理主进程和 Worker 进程之间的进程间通信
使用 ZeroMQ 作为底层实现，但对外隐藏技术细节
"""

import zmq
import zmq.asyncio
from typing import Dict, Optional, Callable, Any, List, Set
import asyncio
from loguru import logger

from .protocol import Message, MessageType, serialize_message, deserialize_message


class CommManager:
    """
    通信管理器（主进程使用）

    管理所有通信连接，提供数据发布、控制命令发送和状态接收功能
    底层使用 ZeroMQ 实现，但对外暴露通用接口
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
    ):
        self.host = host
        self.data_port = data_port
        self.control_port = control_port
        self.status_port = status_port

        # 通信上下文
        self._context: Optional[zmq.asyncio.Context] = None

        # 通信端点
        self._data_publisher: Optional[zmq.asyncio.Socket] = None  # 数据分发
        self._control_server: Optional[zmq.asyncio.Socket] = None  # 控制命令
        self._status_collector: Optional[zmq.asyncio.Socket] = None  # 状态收集

        # 运行状态
        self._running = False
        self._tasks: List[asyncio.Task] = []

        # 回调函数
        self._status_handlers: List[Callable[[Message], None]] = []
        self._control_handlers: List[Callable[[str, Message], None]] = []

    async def start(self) -> bool:
        """
        启动通信服务

        Returns:
            是否启动成功
        """
        try:
            self._context = zmq.asyncio.Context()

            # 创建数据发布端点
            self._data_publisher = self._context.socket(zmq.PUB)
            self._data_publisher.bind(f"tcp://{self.host}:{self.data_port}")
            logger.info(f"数据发布服务绑定到 tcp://{self.host}:{self.data_port}")

            # 创建控制服务端点
            self._control_server = self._context.socket(zmq.ROUTER)
            self._control_server.bind(f"tcp://{self.host}:{self.control_port}")
            logger.info(f"控制服务绑定到 tcp://{self.host}:{self.control_port}")

            # 创建状态收集端点
            self._status_collector = self._context.socket(zmq.PULL)
            self._status_collector.bind(f"tcp://{self.host}:{self.status_port}")
            logger.info(f"状态收集服务绑定到 tcp://{self.host}:{self.status_port}")

            self._running = True

            # 启动后台任务
            self._tasks.append(asyncio.create_task(self._status_loop()))
            self._tasks.append(asyncio.create_task(self._control_loop()))

            logger.info("通信管理器已启动")
            return True

        except Exception as e:
            logger.error(f"启动通信服务失败: {e}")
            await self.stop()
            return False

    async def stop(self) -> bool:
        """
        停止通信服务

        Returns:
            是否停止成功
        """
        self._running = False

        # 取消后台任务
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        # 关闭通信端点
        for endpoint in [self._data_publisher, self._control_server, self._status_collector]:
            if endpoint:
                endpoint.close()

        self._data_publisher = None
        self._control_server = None
        self._status_collector = None

        # 终止上下文
        if self._context:
            self._context.term()
            self._context = None

        logger.info("通信管理器已停止")
        return True

    async def publish_data(self, topic: str, message: Message) -> bool:
        """
        发布市场数据

        Args:
            topic: 主题（如 "market.BTC/USDT.kline"）
            message: 消息

        Returns:
            是否发送成功
        """
        try:
            if self._data_publisher and self._running:
                data = serialize_message(message)
                await self._data_publisher.send_multipart([topic.encode(), data])
                return True
        except Exception as e:
            logger.error(f"发布数据失败: {e}")
        return False

    async def send_control(self, worker_id: str, message: Message) -> bool:
        """
        发送控制命令到指定 Worker

        Args:
            worker_id: Worker ID
            message: 控制消息

        Returns:
            是否发送成功
        """
        try:
            if self._control_server and self._running:
                data = serialize_message(message)
                await self._control_server.send_multipart(
                    [worker_id.encode(), b"", data]
                )
                return True
        except Exception as e:
            logger.error(f"发送控制命令失败: {e}")
        return False

    async def broadcast_control(self, message: Message) -> bool:
        """
        广播控制命令到所有 Worker

        Args:
            message: 控制消息

        Returns:
            是否发送成功
        """
        try:
            if self._data_publisher and self._running:
                data = serialize_message(message)
                await self._data_publisher.send_multipart([b"control.all", data])
                return True
        except Exception as e:
            logger.error(f"广播控制命令失败: {e}")
        return False

    def register_status_handler(self, handler: Callable[[Message], None]):
        """
        注册状态消息处理器

        Args:
            handler: 处理函数，接收 Message 参数
        """
        self._status_handlers.append(handler)

    def unregister_status_handler(self, handler: Callable[[Message], None]):
        """
        注销状态消息处理器

        Args:
            handler: 处理函数
        """
        if handler in self._status_handlers:
            self._status_handlers.remove(handler)

    def register_control_handler(self, handler: Callable[[str, Message], None]):
        """
        注册控制响应处理器

        Args:
            handler: 处理函数，接收 (worker_id, message) 参数
        """
        self._control_handlers.append(handler)

    async def _status_loop(self):
        """状态消息接收循环"""
        while self._running:
            try:
                if self._status_collector:
                    data = await self._status_collector.recv()
                    message = deserialize_message(data)

                    # 调用所有状态处理器
                    for handler in self._status_handlers:
                        try:
                            handler(message)
                        except Exception as e:
                            logger.error(f"状态处理器错误: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收状态消息错误: {e}")
                await asyncio.sleep(0.1)

    async def _control_loop(self):
        """控制响应接收循环"""
        while self._running:
            try:
                if self._control_server:
                    parts = await self._control_server.recv_multipart()
                    if len(parts) >= 3:
                        worker_id = parts[0].decode()
                        data = parts[2]
                        message = deserialize_message(data)

                        # 调用所有控制处理器
                        for handler in self._control_handlers:
                            try:
                                handler(worker_id, message)
                            except Exception as e:
                                logger.error(f"控制处理器错误: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收控制响应错误: {e}")
                await asyncio.sleep(0.1)
