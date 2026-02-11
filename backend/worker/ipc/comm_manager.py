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


class WorkerCommClient:
    """
    Worker 进程的通信客户端

    连接到主进程的通信服务，接收数据和命令，发送状态
    """

    def __init__(
        self,
        worker_id: str,
        host: str = "127.0.0.1",
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
    ):
        self.worker_id = worker_id
        self.host = host
        self.data_port = data_port
        self.control_port = control_port
        self.status_port = status_port

        # 通信上下文
        self._context: Optional[zmq.asyncio.Context] = None

        # 通信端点
        self._data_subscriber: Optional[zmq.asyncio.Socket] = None  # 接收数据
        self._control_client: Optional[zmq.asyncio.Socket] = None  # 接收控制
        self._status_sender: Optional[zmq.asyncio.Socket] = None  # 发送状态

        # 运行状态
        self._connected = False
        self._subscribed_topics: Set[str] = set()

        # 回调函数
        self._data_handlers: List[Callable[[str, Message], None]] = []
        self._control_handlers: List[Callable[[Message], None]] = []

    async def connect(self) -> bool:
        """
        连接到主进程的通信服务

        Returns:
            是否连接成功
        """
        try:
            self._context = zmq.asyncio.Context()

            # 创建数据订阅端点
            self._data_subscriber = self._context.socket(zmq.SUB)
            self._data_subscriber.connect(f"tcp://{self.host}:{self.data_port}")
            # 默认订阅控制广播
            self._data_subscriber.setsockopt(zmq.SUBSCRIBE, b"control.all")
            logger.info(f"数据订阅连接到 tcp://{self.host}:{self.data_port}")

            # 创建控制端点
            self._control_client = self._context.socket(zmq.DEALER)
            self._control_client.identity = self.worker_id.encode()
            self._control_client.connect(f"tcp://{self.host}:{self.control_port}")
            logger.info(f"控制连接到 tcp://{self.host}:{self.control_port}")

            # 创建状态发送端点
            self._status_sender = self._context.socket(zmq.PUSH)
            self._status_sender.connect(f"tcp://{self.host}:{self.status_port}")
            logger.info(f"状态发送连接到 tcp://{self.host}:{self.status_port}")

            self._connected = True

            # 启动后台任务
            asyncio.create_task(self._data_loop())
            asyncio.create_task(self._control_loop())

            logger.info(f"Worker {self.worker_id} 通信客户端已连接")
            return True

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 连接通信服务失败: {e}")
            await self.disconnect()
            return False

    async def disconnect(self) -> bool:
        """
        断开与主进程的连接

        Returns:
            是否断开成功
        """
        self._connected = False

        # 关闭通信端点
        for endpoint in [self._data_subscriber, self._control_client, self._status_sender]:
            if endpoint:
                endpoint.close()

        self._data_subscriber = None
        self._control_client = None
        self._status_sender = None

        # 终止上下文
        if self._context:
            self._context.term()
            self._context = None

        logger.info(f"Worker {self.worker_id} 通信客户端已断开")
        return True

    def subscribe(self, topic: str) -> bool:
        """
        订阅主题

        Args:
            topic: 主题（如 "market.BTC/USDT.kline"）

        Returns:
            是否订阅成功
        """
        try:
            if self._data_subscriber and self._connected:
                self._data_subscriber.setsockopt(zmq.SUBSCRIBE, topic.encode())
                self._subscribed_topics.add(topic)
                logger.debug(f"Worker {self.worker_id} 订阅主题: {topic}")
                return True
        except Exception as e:
            logger.error(f"订阅主题失败: {e}")
        return False

    def subscribe_symbols(self, symbols: List[str], data_types: List[str] = None) -> bool:
        """
        订阅多个交易对的数据

        Args:
            symbols: 交易对列表
            data_types: 数据类型列表，默认为 ["kline"]

        Returns:
            是否订阅成功
        """
        if data_types is None:
            data_types = ["kline"]

        success = True
        for symbol in symbols:
            for data_type in data_types:
                topic = f"market.{symbol}.{data_type}"
                if not self.subscribe(topic):
                    success = False

        return success

    def unsubscribe(self, topic: str) -> bool:
        """
        取消订阅主题

        Args:
            topic: 主题

        Returns:
            是否取消成功
        """
        try:
            if self._data_subscriber and self._connected:
                self._data_subscriber.setsockopt(zmq.UNSUBSCRIBE, topic.encode())
                self._subscribed_topics.discard(topic)
                logger.debug(f"Worker {self.worker_id} 取消订阅主题: {topic}")
                return True
        except Exception as e:
            logger.error(f"取消订阅主题失败: {e}")
        return False

    async def send_status(self, message: Message) -> bool:
        """
        发送状态消息到主进程

        Args:
            message: 状态消息

        Returns:
            是否发送成功
        """
        try:
            if self._status_sender and self._connected:
                message.worker_id = self.worker_id
                data = serialize_message(message)
                await self._status_sender.send(data)
                return True
        except Exception as e:
            logger.error(f"发送状态消息失败: {e}")
        return False

    async def send_control_response(self, message: Message) -> bool:
        """
        发送控制响应到主进程

        Args:
            message: 响应消息

        Returns:
            是否发送成功
        """
        try:
            if self._control_client and self._connected:
                message.worker_id = self.worker_id
                data = serialize_message(message)
                await self._control_client.send(data)
                return True
        except Exception as e:
            logger.error(f"发送控制响应失败: {e}")
        return False

    def register_data_handler(self, handler: Callable[[str, Message], None]):
        """
        注册数据消息处理器

        Args:
            handler: 处理函数，接收 (topic, message) 参数
        """
        self._data_handlers.append(handler)

    def unregister_data_handler(self, handler: Callable[[str, Message], None]):
        """
        注销数据消息处理器

        Args:
            handler: 处理函数
        """
        if handler in self._data_handlers:
            self._data_handlers.remove(handler)

    def register_control_handler(self, handler: Callable[[Message], None]):
        """
        注册控制命令处理器

        Args:
            handler: 处理函数，接收 message 参数
        """
        self._control_handlers.append(handler)

    async def _data_loop(self):
        """数据接收循环"""
        while self._connected:
            try:
                if self._data_subscriber:
                    topic, data = await self._data_subscriber.recv_multipart()
                    message = deserialize_message(data)

                    # 调用所有数据处理器
                    for handler in self._data_handlers:
                        try:
                            handler(topic.decode(), message)
                        except Exception as e:
                            logger.error(f"数据处理器错误: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收数据错误: {e}")
                await asyncio.sleep(0.1)

    async def _control_loop(self):
        """控制命令接收循环"""
        while self._connected:
            try:
                if self._control_client:
                    data = await self._control_client.recv()
                    message = deserialize_message(data)

                    # 调用所有控制处理器
                    for handler in self._control_handlers:
                        try:
                            handler(message)
                        except Exception as e:
                            logger.error(f"控制处理器错误: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收控制命令错误: {e}")
                await asyncio.sleep(0.1)
