# -*- coding: utf-8 -*-
"""
Nautilus 日志订阅器

订阅 Worker 的日志消息并处理，通常运行在主进程中。
使用 pyzmq 的 SUB socket 接收日志。

使用示例:
    subscriber = NautilusLogSubscriber(
        worker_id="001",
        pub_port=5560,
        log_handler=handle_log,
    )
    await subscriber.start()
    
    # 处理日志...
    
    subscriber.stop()
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine, Optional, Union

import zmq
import zmq.asyncio

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)


# 日志处理器类型
LogHandler = Callable[[dict[str, Any]], Union[None, Coroutine[Any, Any, None]]]


class NautilusLogSubscriber:
    """
    Nautilus 日志订阅器

    订阅 Worker 的日志消息并处理。支持同步和异步的日志处理器。
    """

    def __init__(
        self,
        worker_id: str,
        pub_port: int = 5560,
        log_handler: Optional[LogHandler] = None,
        auto_reconnect: bool = True,
        reconnect_interval: float = 5.0,
    ):
        """
        初始化日志订阅器

        Parameters
        ----------
        worker_id : str
            Worker ID
        pub_port : int
            ZMQ PUB 端口
        log_handler : Optional[LogHandler]
            日志处理器函数，接收日志字典
        auto_reconnect : bool
            是否自动重连
        reconnect_interval : float
            重连间隔（秒）
        """
        self.worker_id = worker_id
        self.pub_port = pub_port
        self.log_handler = log_handler
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval

        # ZMQ 相关
        self._context: Optional[zmq.asyncio.Context] = None
        self._sub_socket: Optional[zmq.asyncio.Socket] = None
        self._running = False

        # 接收任务
        self._receive_task: Optional[asyncio.Task] = None

        # 统计
        self._logs_received = 0
        self._logs_processed = 0
        self._logs_error = 0

    async def start(self) -> bool:
        """
        启动日志订阅器

        Returns
        -------
        bool
            是否启动成功
        """
        try:
            if self._running:
                return True

            # 创建 ZMQ 上下文和 SUB socket
            self._context = zmq.asyncio.Context()
            self._sub_socket = self._context.socket(zmq.SUB)
            self._sub_socket.setsockopt(zmq.RCVHWM, 1000)  # 接收高水位标记
            self._sub_socket.setsockopt(zmq.RCVTIMEO, 1000)  # 接收超时

            # 连接到 PUB 端点
            self._sub_socket.connect(f"tcp://127.0.0.1:{self.pub_port}")

            # 订阅该 Worker 的所有日志
            topic_filter = f"log.{self.worker_id}."
            self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, topic_filter)

            self._running = True

            # 启动接收任务
            self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info(
                f"NautilusLogSubscriber 已启动: worker_id={self.worker_id}, "
                f"pub_port={self.pub_port}, filter={topic_filter}"
            )

            return True

        except Exception as e:
            logger.error(f"NautilusLogSubscriber 启动失败: {e}")
            await self.stop()
            return False

    async def stop(self) -> None:
        """停止日志订阅器"""
        if not self._running:
            return

        self._running = False

        # 取消接收任务
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # 关闭 ZMQ socket
        if self._sub_socket:
            try:
                self._sub_socket.close()
            except Exception:
                pass
            self._sub_socket = None

        # 终止 ZMQ 上下文
        if self._context:
            try:
                self._context.term()
            except Exception:
                pass
            self._context = None

        logger.info(
            f"NautilusLogSubscriber 已停止: worker_id={self.worker_id}, "
            f"received={self._logs_received}, processed={self._logs_processed}, "
            f"errors={self._logs_error}"
        )

    async def _receive_loop(self) -> None:
        """接收日志循环"""
        while self._running:
            try:
                if not self._sub_socket:
                    if self.auto_reconnect:
                        await asyncio.sleep(self.reconnect_interval)
                        await self._reconnect()
                    continue

                # 接收消息
                try:
                    topic, data = await self._sub_socket.recv_multipart()
                except zmq.Again:
                    # 超时，继续循环
                    continue
                except zmq.ZMQError as e:
                    if e.errno == zmq.ETERM:
                        # 上下文已终止
                        break
                    raise

                self._logs_received += 1

                # 解析日志
                try:
                    log_entry = json.loads(data.decode("utf-8"))
                except json.JSONDecodeError as e:
                    logger.warning(f"解析日志 JSON 失败: {e}")
                    self._logs_error += 1
                    continue

                # 调用处理器
                if self.log_handler:
                    try:
                        result = self.log_handler(log_entry)
                        # 如果是协程，等待完成
                        if asyncio.iscoroutine(result):
                            await result
                        self._logs_processed += 1
                    except Exception as e:
                        logger.error(f"处理日志失败: {e}")
                        self._logs_error += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"接收日志循环错误: {e}")
                if self.auto_reconnect and self._running:
                    await asyncio.sleep(self.reconnect_interval)
                else:
                    break

    async def _reconnect(self) -> bool:
        """重新连接"""
        try:
            # 关闭旧 socket
            if self._sub_socket:
                self._sub_socket.close()
                self._sub_socket = None

            # 创建新 socket
            self._sub_socket = self._context.socket(zmq.SUB)
            self._sub_socket.setsockopt(zmq.RCVHWM, 1000)
            self._sub_socket.setsockopt(zmq.RCVTIMEO, 1000)

            # 连接
            self._sub_socket.connect(f"tcp://127.0.0.1:{self.pub_port}")
            topic_filter = f"log.{self.worker_id}."
            self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, topic_filter)

            logger.info(f"NautilusLogSubscriber 重新连接成功: worker_id={self.worker_id}")
            return True

        except Exception as e:
            logger.error(f"NautilusLogSubscriber 重新连接失败: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "worker_id": self.worker_id,
            "pub_port": self.pub_port,
            "running": self._running,
            "logs_received": self._logs_received,
            "logs_processed": self._logs_processed,
            "logs_error": self._logs_error,
        }


class NautilusLogSubscriberManager:
    """
    Nautilus 日志订阅器管理器

    管理多个 Worker 的日志订阅器，通常由 CommManager 使用。
    """

    def __init__(self, base_port: int = 5560):
        """
        初始化管理器

        Parameters
        ----------
        base_port : int
            基础端口
        """
        self.base_port = base_port
        self._subscribers: dict[str, NautilusLogSubscriber] = {}
        self._log_handler: Optional[LogHandler] = None

    def set_log_handler(self, handler: LogHandler) -> None:
        """
        设置全局日志处理器

        Parameters
        ----------
        handler : LogHandler
            日志处理器函数
        """
        self._log_handler = handler

    async def add_worker(self, worker_id: str) -> bool:
        """
        添加 Worker 订阅

        Parameters
        ----------
        worker_id : str
            Worker ID

        Returns
        -------
        bool
            是否添加成功
        """
        if worker_id in self._subscribers:
            return True

        try:
            # 计算端口
            try:
                worker_id_int = int(worker_id)
                pub_port = self.base_port + worker_id_int
            except ValueError:
                pub_port = self.base_port + (hash(worker_id) % 1000)

            # 创建订阅器
            subscriber = NautilusLogSubscriber(
                worker_id=worker_id,
                pub_port=pub_port,
                log_handler=self._log_handler,
            )

            # 启动
            if await subscriber.start():
                self._subscribers[worker_id] = subscriber
                logger.info(f"已添加 Worker {worker_id} 的日志订阅")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"添加 Worker {worker_id} 的日志订阅失败: {e}")
            return False

    async def remove_worker(self, worker_id: str) -> None:
        """
        移除 Worker 订阅

        Parameters
        ----------
        worker_id : str
            Worker ID
        """
        if worker_id not in self._subscribers:
            return

        subscriber = self._subscribers.pop(worker_id)
        await subscriber.stop()
        logger.info(f"已移除 Worker {worker_id} 的日志订阅")

    async def stop_all(self) -> None:
        """停止所有订阅器"""
        for worker_id, subscriber in list(self._subscribers.items()):
            await subscriber.stop()
        self._subscribers.clear()
        logger.info("已停止所有日志订阅器")

    def get_stats(self) -> dict[str, Any]:
        """获取所有订阅器的统计信息"""
        return {
            "base_port": self.base_port,
            "worker_count": len(self._subscribers),
            "workers": {
                worker_id: subscriber.get_stats()
                for worker_id, subscriber in self._subscribers.items()
            },
        }


def create_log_handler_for_db(
    db_session_factory: Callable,
) -> LogHandler:
    """
    创建数据库日志处理器

    将日志写入数据库的处理器工厂函数。

    Parameters
    ----------
    db_session_factory : Callable
        数据库会话工厂

    Returns
    -------
    LogHandler
        日志处理器函数
    """

    async def handle_log(log_entry: dict[str, Any]) -> None:
        """处理日志并写入数据库"""
        try:
            # 这里应该写入数据库
            # 示例代码，实际需要根据数据库模型实现
            logger.debug(
                f"[DB] [{log_entry['level']}] {log_entry['component']}: "
                f"{log_entry['message'][:50]}..."
            )

            # TODO: 实际写入数据库
            # async with db_session_factory() as session:
            #     log_record = LogRecord(
            #         worker_id=log_entry['worker_id'],
            #         timestamp=log_entry['timestamp'],
            #         level=log_entry['level'],
            #         component=log_entry['component'],
            #         message=log_entry['message'],
            #     )
            #     session.add(log_record)
            #     await session.commit()

        except Exception as e:
            logger.error(f"写入日志到数据库失败: {e}")

    return handle_log


__all__ = [
    "NautilusLogSubscriber",
    "NautilusLogSubscriberManager",
    "LogHandler",
    "create_log_handler_for_db",
]