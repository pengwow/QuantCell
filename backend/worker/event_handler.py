# -*- coding: utf-8 -*-
"""
Worker 事件处理器模块

提供事件处理功能，支持：
- 订单事件处理
- 成交事件处理
- 持仓事件处理
- 事件同步到主进程

使用示例：
    from worker.event_handler import EventHandler

    handler = EventHandler(worker_id, comm_client)
    await handler.start()
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class EventBufferConfig:
    """事件缓冲配置"""
    buffer_size: int = 1000
    flush_interval: float = 1.0
    batch_size: int = 100


class EventHandler:
    """
    事件处理器

    负责处理 Worker 中的各类事件，并将事件同步到主进程。
    """

    def __init__(
        self,
        worker_id: str,
        comm_client: Any,
        config: Optional[EventBufferConfig] = None,
    ):
        self.worker_id = worker_id
        self.comm_client = comm_client
        self.config = config or EventBufferConfig()

        # 事件缓冲
        self._event_buffer: deque = deque(maxlen=self.config.buffer_size)
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

        # 统计
        self._events_received = 0
        self._events_sent = 0
        self._events_dropped = 0

    async def start(self) -> None:
        """启动事件处理器"""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"Worker {self.worker_id} 事件处理器已启动")

    async def stop(self) -> None:
        """停止事件处理器"""
        if not self._running:
            return

        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # 刷新剩余事件
        await self._flush_buffer()

        logger.info(f"Worker {self.worker_id} 事件处理器已停止")

    def on_order_event(self, event: Dict[str, Any]) -> None:
        """处理订单事件"""
        self._events_received += 1
        self._buffer_event({
            "type": "order",
            "data": event,
            "timestamp": datetime.now().isoformat(),
        })

    def on_fill_event(self, event: Dict[str, Any]) -> None:
        """处理成交事件"""
        self._events_received += 1
        self._buffer_event({
            "type": "fill",
            "data": event,
            "timestamp": datetime.now().isoformat(),
        })
        # 成交事件立即发送（如果有运行的事件循环）
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._flush_buffer())
        except RuntimeError:
            # 没有运行的事件循环，不立即刷新
            pass

    def on_position_event(self, event: Dict[str, Any]) -> None:
        """处理持仓事件"""
        self._events_received += 1
        self._buffer_event({
            "type": "position",
            "data": event,
            "timestamp": datetime.now().isoformat(),
        })

    def _buffer_event(self, event: Dict[str, Any]) -> None:
        """将事件添加到缓冲队列"""
        if len(self._event_buffer) >= self.config.buffer_size:
            self._events_dropped += 1
            logger.warning(f"Worker {self.worker_id} 事件缓冲区已满，丢弃事件")

        self._event_buffer.append(event)

        # 达到批量大小立即刷新（如果有运行的事件循环）
        if len(self._event_buffer) >= self.config.batch_size:
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(self._flush_buffer())
            except RuntimeError:
                # 没有运行的事件循环，等待定时刷新
                pass

    async def _flush_loop(self) -> None:
        """定时刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval)
                if self._event_buffer:
                    await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} 事件刷新循环错误: {e}")

    async def _flush_buffer(self) -> None:
        """刷新缓冲队列到主进程"""
        if not self._event_buffer:
            return

        events = list(self._event_buffer)
        self._event_buffer.clear()

        try:
            if self.comm_client:
                for event in events:
                    await self.comm_client.send_event(event)
                self._events_sent += len(events)
        except Exception as e:
            logger.error(f"Worker {self.worker_id} 发送事件失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "events_received": self._events_received,
            "events_sent": self._events_sent,
            "events_dropped": self._events_dropped,
            "buffer_size": len(self._event_buffer),
        }


__all__ = [
    "EventHandler",
    "EventBufferConfig",
]
