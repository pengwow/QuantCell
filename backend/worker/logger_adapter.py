# -*- coding: utf-8 -*-
"""
Nautilus 日志适配器

捕获 Nautilus 的日志并通过 ZMQ PUB 发布到主进程。
使用 pyzmq 的 PUB/SUB 模式，替代 stdout 桥接方案。

使用示例:
    adapter = NautilusLoggerAdapter(worker_id="001", pub_port=5560)
    adapter.start()
    
    # 发布日志
    await adapter.publish_log("INFO", "TradingNode", "Strategy started")
    
    adapter.stop()
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Optional

import zmq
import zmq.asyncio

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)


class NautilusLoggerAdapter:
    """
    Nautilus 日志适配器

    捕获 Nautilus 的日志并通过 ZMQ PUB 发布。
    支持两种模式:
    1. 直接发布模式: 调用 publish_log() 直接发布
    2. 队列模式: 通过 QueueHandler 收集日志后批量发布
    """

    def __init__(
        self,
        worker_id: str,
        pub_port: int = 5560,
        max_queue_size: int = 10000,
        flush_interval: float = 0.1,
        batch_size: int = 100,
    ):
        """
        初始化日志适配器

        Parameters
        ----------
        worker_id : str
            Worker ID
        pub_port : int
            ZMQ PUB 端口
        max_queue_size : int
            内部队列最大大小
        flush_interval : float
            刷新间隔（秒）
        batch_size : int
            批量发送大小
        """
        self.worker_id = worker_id
        self.pub_port = pub_port
        self.max_queue_size = max_queue_size
        self.flush_interval = flush_interval
        self.batch_size = batch_size

        # ZMQ 相关
        self._context: Optional[zmq.asyncio.Context] = None
        self._pub_socket: Optional[zmq.asyncio.Socket] = None
        self._running = False

        # 日志队列
        self._log_queue: Queue[dict] = Queue(maxsize=max_queue_size)

        # 后台任务
        self._flush_thread: Optional[threading.Thread] = None

        # 统计
        self._logs_received = 0
        self._logs_sent = 0
        self._logs_dropped = 0

    def start(self) -> bool:
        """
        启动日志适配器

        Returns
        -------
        bool
            是否启动成功
        """
        try:
            if self._running:
                return True

            # 创建 ZMQ 上下文和 PUB socket
            self._context = zmq.asyncio.Context()
            self._pub_socket = self._context.socket(zmq.PUB)
            self._pub_socket.setsockopt(zmq.SNDHWM, 1000)  # 发送高水位标记
            self._pub_socket.setsockopt(zmq.LINGER, 100)  # 关闭时等待时间
            self._pub_socket.bind(f"tcp://127.0.0.1:{self.pub_port}")

            self._running = True

            # 启动后台刷新线程
            self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
            self._flush_thread.start()

            logger.info(
                f"NautilusLoggerAdapter 已启动: worker_id={self.worker_id}, "
                f"pub_port={self.pub_port}"
            )

            # 等待 socket 就绪
            time.sleep(0.1)

            return True

        except Exception as e:
            logger.error(f"NautilusLoggerAdapter 启动失败: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        """停止日志适配器"""
        if not self._running:
            return

        self._running = False

        # 等待刷新线程结束
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=2.0)

        # 刷新剩余日志
        self._flush_remaining()

        # 关闭 ZMQ socket
        if self._pub_socket:
            try:
                self._pub_socket.close()
            except Exception:
                pass
            self._pub_socket = None

        # 终止 ZMQ 上下文
        if self._context:
            try:
                self._context.term()
            except Exception:
                pass
            self._context = None

        logger.info(
            f"NautilusLoggerAdapter 已停止: worker_id={self.worker_id}, "
            f"received={self._logs_received}, sent={self._logs_sent}, "
            f"dropped={self._logs_dropped}"
        )

    def enqueue_log(
        self,
        level: str,
        component: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        将日志加入队列（线程安全）

        此方法可以在任何线程中调用，日志会被放入队列后批量发送。

        Parameters
        ----------
        level : str
            日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        component : str
            组件名称
        message : str
            日志消息
        timestamp : Optional[datetime]
            时间戳，默认为当前时间

        Returns
        -------
        bool
            是否成功加入队列
        """
        try:
            if not self._running:
                return False

            if self._log_queue.full():
                self._logs_dropped += 1
                return False

            log_entry = {
                "worker_id": self.worker_id,
                "timestamp": (timestamp or datetime.now()).isoformat(),
                "level": level.upper(),
                "component": component,
                "message": message,
            }

            self._log_queue.put_nowait(log_entry)
            self._logs_received += 1
            return True

        except Exception as e:
            logger.debug(f"加入日志队列失败: {e}")
            return False

    async def publish_log(
        self,
        level: str,
        component: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        直接发布日志（异步）

        此方法直接发送日志，不经过队列。适合低频日志或重要日志。

        Parameters
        ----------
        level : str
            日志级别
        component : str
            组件名称
        message : str
            日志消息
        timestamp : Optional[datetime]
            时间戳

        Returns
        -------
        bool
            是否发送成功
        """
        if not self._running or not self._pub_socket:
            return False

        try:
            log_entry = {
                "worker_id": self.worker_id,
                "timestamp": (timestamp or datetime.now()).isoformat(),
                "level": level.upper(),
                "component": component,
                "message": message,
            }

            topic = f"log.{self.worker_id}.{level.lower()}"
            data = json.dumps(log_entry, ensure_ascii=False)

            await self._pub_socket.send_multipart(
                [topic.encode(), data.encode()],
                flags=zmq.NOBLOCK,
            )

            self._logs_sent += 1
            return True

        except zmq.Again:
            # 发送缓冲区满
            self._logs_dropped += 1
            return False
        except Exception as e:
            logger.debug(f"发布日志失败: {e}")
            return False

    def _flush_loop(self) -> None:
        """后台刷新循环（在独立线程中运行）"""
        # 创建新的 event loop 用于异步操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self._running:
            try:
                # 批量获取日志
                logs = []
                try:
                    # 等待第一条日志
                    log = self._log_queue.get(timeout=self.flush_interval)
                    logs.append(log)

                    # 批量获取更多日志
                    while len(logs) < self.batch_size:
                        try:
                            log = self._log_queue.get_nowait()
                            logs.append(log)
                        except Empty:
                            break
                except Empty:
                    continue

                # 发送日志
                if logs and self._pub_socket:
                    loop.run_until_complete(self._send_batch(logs))

            except Exception as e:
                logger.debug(f"刷新循环错误: {e}")
                time.sleep(0.01)

        loop.close()

    async def _send_batch(self, logs: list[dict]) -> None:
        """批量发送日志"""
        if not self._pub_socket:
            return

        for log in logs:
            try:
                topic = f"log.{self.worker_id}.{log['level'].lower()}"
                data = json.dumps(log, ensure_ascii=False)

                await self._pub_socket.send_multipart(
                    [topic.encode(), data.encode()],
                    flags=zmq.NOBLOCK,
                )

                self._logs_sent += 1

            except zmq.Again:
                self._logs_dropped += 1
            except Exception as e:
                logger.debug(f"发送日志失败: {e}")

    def _flush_remaining(self) -> None:
        """刷新剩余日志"""
        if not self._pub_socket:
            return

        logs = []
        try:
            while not self._log_queue.empty():
                logs.append(self._log_queue.get_nowait())
        except Empty:
            pass

        if logs:
            # 创建临时 event loop 发送
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._send_batch(logs))
            finally:
                loop.close()

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "worker_id": self.worker_id,
            "pub_port": self.pub_port,
            "running": self._running,
            "logs_received": self._logs_received,
            "logs_sent": self._logs_sent,
            "logs_dropped": self._logs_dropped,
            "queue_size": self._log_queue.qsize(),
        }


class NautilusLogQueueHandler:
    """
    Nautilus 日志队列处理器

    作为 Python logging 的 Handler 使用，将日志放入 NautilusLoggerAdapter 的队列。
    这样可以捕获标准 logging 的日志并通过 ZMQ 发送。

    使用示例:
        adapter = NautilusLoggerAdapter(worker_id="001", pub_port=5560)
        adapter.start()

        # 创建队列处理器
        queue_handler = NautilusLogQueueHandler(adapter)
        queue_handler.setLevel(logging.INFO)

        # 添加到 logger
        nautilus_logger = logging.getLogger("nautilus_trader")
        nautilus_logger.addHandler(queue_handler)
    """

    def __init__(self, adapter: NautilusLoggerAdapter):
        """
        初始化队列处理器

        Parameters
        ----------
        adapter : NautilusLoggerAdapter
            日志适配器实例
        """
        super().__init__()
        self.adapter = adapter

    def emit(self, record) -> None:
        """
        处理日志记录

        Parameters
        ----------
        record : logging.LogRecord
            日志记录
        """
        try:
            # 格式化消息
            message = self.format(record)

            # 提取组件名称（从 logger name）
            component = record.name
            if component.startswith("nautilus_trader."):
                component = component.replace("nautilus_trader.", "")

            # 加入队列
            self.adapter.enqueue_log(
                level=record.levelname,
                component=component,
                message=message,
                timestamp=datetime.fromtimestamp(record.created),
            )

        except Exception:
            self.handleError(record)


def create_nautilus_log_adapter(
    worker_id: str,
    base_port: int = 5560,
) -> NautilusLoggerAdapter:
    """
    创建 Nautilus 日志适配器的便捷函数

    Parameters
    ----------
    worker_id : str
        Worker ID
    base_port : int
        基础端口，实际端口为 base_port + worker_id

    Returns
    -------
    NautilusLoggerAdapter
        日志适配器实例
    """
    try:
        worker_id_int = int(worker_id)
        pub_port = base_port + worker_id_int
    except ValueError:
        # 如果 worker_id 不是数字，使用哈希
        pub_port = base_port + (hash(worker_id) % 1000)

    return NautilusLoggerAdapter(
        worker_id=worker_id,
        pub_port=pub_port,
    )


__all__ = [
    "NautilusLoggerAdapter",
    "NautilusLogQueueHandler",
    "create_nautilus_log_adapter",
]