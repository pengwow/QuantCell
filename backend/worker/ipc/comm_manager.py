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

# 超时配置常量
ZMQ_BIND_TIMEOUT = 5.0  # ZeroMQ bind 操作超时时间（秒）
ZMQ_SEND_TIMEOUT = 3.0  # ZeroMQ 发送操作超时时间（秒）
ZMQ_RECV_TIMEOUT = 1.0  # ZeroMQ 接收操作超时时间（秒）
MAX_BIND_RETRIES = 3  # 最大 bind 重试次数
PORT_RANGE_START = 5555  # 端口范围起始
PORT_RANGE_END = 5600  # 端口范围结束


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

            # 尝试绑定端口，支持自动端口选择
            bind_success = await self._bind_with_retry()
            if not bind_success:
                logger.error("通信服务启动失败：无法绑定端口")
                await self.stop()
                return False

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

    async def _bind_with_retry(self) -> bool:
        """
        尝试绑定端口，支持重试和自动端口选择

        Returns:
            是否绑定成功
        """
        for attempt in range(MAX_BIND_RETRIES):
            try:
                # 创建数据发布端点
                self._data_publisher = self._context.socket(zmq.PUB)
                self._data_publisher.setsockopt(zmq.LINGER, 0)  # 设置关闭时不阻塞
                
                # 使用 asyncio.wait_for 添加超时
                await asyncio.wait_for(
                    self._async_bind(self._data_publisher, self.data_port),
                    timeout=ZMQ_BIND_TIMEOUT
                )
                logger.info(f"数据发布服务绑定到 tcp://{self.host}:{self.data_port}")

                # 创建控制服务端点
                self._control_server = self._context.socket(zmq.ROUTER)
                self._control_server.setsockopt(zmq.LINGER, 0)
                await asyncio.wait_for(
                    self._async_bind(self._control_server, self.control_port),
                    timeout=ZMQ_BIND_TIMEOUT
                )
                logger.info(f"控制服务绑定到 tcp://{self.host}:{self.control_port}")

                # 创建状态收集端点
                self._status_collector = self._context.socket(zmq.PULL)
                self._status_collector.setsockopt(zmq.LINGER, 0)
                await asyncio.wait_for(
                    self._async_bind(self._status_collector, self.status_port),
                    timeout=ZMQ_BIND_TIMEOUT
                )
                logger.info(f"状态收集服务绑定到 tcp://{self.host}:{self.status_port}")

                return True

            except asyncio.TimeoutError:
                logger.warning(f"端口绑定超时 (尝试 {attempt + 1}/{MAX_BIND_RETRIES})")
                await self._cleanup_sockets()
                
                # 尝试使用随机端口
                if attempt < MAX_BIND_RETRIES - 1:
                    import random
                    self.data_port = random.randint(PORT_RANGE_START, PORT_RANGE_END)
                    self.control_port = random.randint(PORT_RANGE_START, PORT_RANGE_END)
                    self.status_port = random.randint(PORT_RANGE_START, PORT_RANGE_END)
                    logger.info(f"尝试使用新端口: data={self.data_port}, control={self.control_port}, status={self.status_port}")
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"绑定端口失败: {e}")
                await self._cleanup_sockets()
                if attempt < MAX_BIND_RETRIES - 1:
                    await asyncio.sleep(0.1)

        return False

    async def _async_bind(self, socket: zmq.asyncio.Socket, port: int):
        """
        异步执行 bind 操作
        
        Args:
            socket: ZeroMQ socket
            port: 端口号
        """
        # 在线程池中执行阻塞的 bind 操作
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            socket.bind, 
            f"tcp://{self.host}:{port}"
        )

    async def _cleanup_sockets(self):
        """清理已创建的 socket"""
        for socket in [self._data_publisher, self._control_server, self._status_collector]:
            if socket:
                try:
                    socket.close()
                except:
                    pass
        self._data_publisher = None
        self._control_server = None
        self._status_collector = None

    async def stop(self) -> bool:
        """
        停止通信服务

        Returns:
            是否停止成功
        """
        self._running = False

        # 取消后台任务，设置超时
        for task in self._tasks:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._tasks.clear()

        # 关闭通信端点
        await self._cleanup_sockets()

        # 终止上下文
        if self._context:
            try:
                self._context.term()
            except:
                pass
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
                await asyncio.wait_for(
                    self._data_publisher.send_multipart([topic.encode(), data]),
                    timeout=ZMQ_SEND_TIMEOUT
                )
                return True
        except asyncio.TimeoutError:
            logger.warning(f"发布数据超时: {topic}")
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
                await asyncio.wait_for(
                    self._control_server.send_multipart(
                        [worker_id.encode(), b"", data]
                    ),
                    timeout=ZMQ_SEND_TIMEOUT
                )
                return True
        except asyncio.TimeoutError:
            logger.warning(f"发送控制命令超时: worker_id={worker_id}")
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
                await asyncio.wait_for(
                    self._data_publisher.send_multipart([b"control.all", data]),
                    timeout=ZMQ_SEND_TIMEOUT
                )
                return True
        except asyncio.TimeoutError:
            logger.warning("广播控制命令超时")
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
                    # 使用超时接收，避免永久阻塞
                    if await self._status_collector.poll(timeout=int(ZMQ_RECV_TIMEOUT * 1000)):
                        data = await self._status_collector.recv()
                        message = deserialize_message(data)

                        # 调用所有状态处理器
                        for handler in self._status_handlers:
                            try:
                                handler(message)
                            except Exception as e:
                                logger.error(f"状态处理器错误: {e}")
                    else:
                        # 超时，继续循环检查运行状态
                        await asyncio.sleep(0.01)
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
                    # 使用超时接收
                    if await self._control_server.poll(timeout=int(ZMQ_RECV_TIMEOUT * 1000)):
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
                    else:
                        # 超时，继续循环
                        await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收控制响应错误: {e}")
                await asyncio.sleep(0.1)
