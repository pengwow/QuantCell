# -*- coding: utf-8 -*-
"""
Nautilus 日志文件监听器

监听 Nautilus 日志文件的变化，将新日志通过 ZMQ 发布到主进程。
替代 stdout 捕获方案，更安全可靠。

使用示例:
    monitor = NautilusLogFileMonitor(
        worker_id="001",
        log_file_path="/tmp/worker_001.log",
        pub_port=5560,
    )
    monitor.start()
    
    # 日志会自动通过 ZMQ 发布
    
    monitor.stop()
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import zmq
import zmq.asyncio

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)


class NautilusLogFileMonitor:
    """
    Nautilus 日志文件监听器

    监听日志文件变化，将新行通过 ZMQ PUB 发布。
    """

    def __init__(
        self,
        worker_id: str,
        log_file_path: str,
        pub_port: int = 5560,
        poll_interval: float = 0.1,
    ):
        """
        初始化日志文件监听器

        Parameters
        ----------
        worker_id : str
            Worker ID
        log_file_path : str
            日志文件路径
        pub_port : int
            ZMQ PUB 端口
        poll_interval : float
            轮询间隔（秒）
        """
        self.worker_id = worker_id
        self.log_file_path = log_file_path
        self.pub_port = pub_port
        self.poll_interval = poll_interval

        # ZMQ 相关
        self._context: Optional[zmq.asyncio.Context] = None
        self._pub_socket: Optional[zmq.asyncio.Socket] = None
        self._running = False

        # 文件监听
        self._monitor_thread: Optional[threading.Thread] = None
        self._file_position = 0

        # 统计
        self._logs_sent = 0

    def start(self) -> bool:
        """
        启动日志监听器

        Returns
        -------
        bool
            是否启动成功
        """
        try:
            if self._running:
                return True

            # 检查日志文件是否存在
            if not os.path.exists(self.log_file_path):
                # 创建空文件
                Path(self.log_file_path).touch()

            # 创建 ZMQ 上下文和 PUB socket
            self._context = zmq.asyncio.Context()
            self._pub_socket = self._context.socket(zmq.PUB)
            self._pub_socket.setsockopt(zmq.SNDHWM, 1000)
            self._pub_socket.setsockopt(zmq.LINGER, 100)
            self._pub_socket.bind(f"tcp://127.0.0.1:{self.pub_port}")

            # 初始化文件位置到文件末尾（不发送历史日志）
            self._file_position = os.path.getsize(self.log_file_path)

            self._running = True

            # 启动监听线程
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

            logger.info(
                f"NautilusLogFileMonitor 已启动: worker_id={self.worker_id}, "
                f"log_file={self.log_file_path}, pub_port={self.pub_port}"
            )

            # 等待 socket 就绪
            time.sleep(0.1)

            return True

        except Exception as e:
            logger.error(f"NautilusLogFileMonitor 启动失败: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        """停止日志监听器"""
        if not self._running:
            return

        self._running = False

        # 等待监听线程结束
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

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
            f"NautilusLogFileMonitor 已停止: worker_id={self.worker_id}, "
            f"logs_sent={self._logs_sent}"
        )

    def _monitor_loop(self) -> None:
        """文件监听循环"""
        # 创建 event loop 用于异步操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self._running:
            try:
                # 检查文件是否存在
                if not os.path.exists(self.log_file_path):
                    time.sleep(self.poll_interval)
                    continue

                # 获取当前文件大小
                current_size = os.path.getsize(self.log_file_path)

                # 如果文件被清空或重置，重新定位
                if current_size < self._file_position:
                    self._file_position = 0

                # 如果有新内容，读取并发送
                if current_size > self._file_position:
                    with open(self.log_file_path, "r", encoding="utf-8") as f:
                        f.seek(self._file_position)
                        new_lines = f.readlines()
                        self._file_position = f.tell()

                    # 发送新日志
                    for line in new_lines:
                        line = line.strip()
                        if line:
                            loop.run_until_complete(self._publish_log(line))

                time.sleep(self.poll_interval)

            except Exception as e:
                logger.debug(f"监听日志文件错误: {e}")
                time.sleep(self.poll_interval)

        loop.close()

    async def _publish_log(self, line: str) -> None:
        """
        发布日志行

        Parameters
        ----------
        line : str
            日志行
        """
        if not self._pub_socket:
            return

        try:
            # 解析 Nautilus 日志格式
            # 格式: 2026-04-01T11:26:33.652350000Z [INFO] TEST-TRADER-001.TradingNode: message
            import re

            match = re.match(
                r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+\[(\w+)\]\s+(.+?):(.*)",
                line
            )

            if match:
                timestamp_str, level, component, message = match.groups()
                log_entry = {
                    "worker_id": self.worker_id,
                    "timestamp": timestamp_str,
                    "level": level.upper(),
                    "component": component.strip(),
                    "message": message.strip(),
                }
            else:
                # 非标准格式，作为原始消息
                log_entry = {
                    "worker_id": self.worker_id,
                    "timestamp": datetime.now().isoformat(),
                    "level": "INFO",
                    "component": "nautilus",
                    "message": line,
                }

            # 发布到 ZMQ
            topic = f"log.{self.worker_id}.{log_entry['level'].lower()}"
            data = json.dumps(log_entry, ensure_ascii=False)

            await self._pub_socket.send_multipart(
                [topic.encode(), data.encode()],
                flags=zmq.NOBLOCK,
            )

            self._logs_sent += 1

        except zmq.Again:
            # 发送缓冲区满，丢弃
            pass
        except Exception as e:
            logger.debug(f"发布日志失败: {e}")

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "worker_id": self.worker_id,
            "log_file_path": self.log_file_path,
            "pub_port": self.pub_port,
            "running": self._running,
            "logs_sent": self._logs_sent,
            "file_position": self._file_position,
        }


def create_log_monitor(
    worker_id: str,
    log_file_path: str,
    base_port: int = 5560,
) -> NautilusLogFileMonitor:
    """
    创建日志监听器的便捷函数

    Parameters
    ----------
    worker_id : str
        Worker ID
    log_file_path : str
        日志文件路径
    base_port : int
        基础端口

    Returns
    -------
    NautilusLogFileMonitor
        日志监听器实例
    """
    try:
        worker_id_int = int(worker_id)
        pub_port = base_port + worker_id_int
    except ValueError:
        pub_port = base_port + (hash(worker_id) % 1000)

    return NautilusLogFileMonitor(
        worker_id=worker_id,
        log_file_path=log_file_path,
        pub_port=pub_port,
    )


__all__ = [
    "NautilusLogFileMonitor",
    "create_log_monitor",
]