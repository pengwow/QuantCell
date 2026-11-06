"""研究事件 WS 发布桥（进程内 pub/sub）。

append_event 由 worker 线程调用（同步 SQLAlchemy 会话），而 WebSocket 连接
活在 FastAPI 主事件循环里，两侧线程不同——用绑定的 event loop +
call_soon_threadsafe 跨线程投递，发布方永不阻塞、永不抛错。

ponytail: 单进程内有效。uvicorn 多 worker 部署时事件只会推到与写入方同进程的
连接；未覆盖的连接与实时性丢失统一靠前端既有事件轮询兜底（升级路径：换
Redis pub/sub）。消息也不补发——事件已持久化，断线连接重连后走轮询续读。
"""

from __future__ import annotations

import asyncio

# 同一 owner 允许多个页面各开一条连接，各自独立队列
_subscribers: dict[str, list[asyncio.Queue]] = {}
_loop: asyncio.AbstractEventLoop | None = None

# 单连接积压上限：超过直接丢新事件（不丢旧），前端用 /events 增量轮询补齐
_QUEUE_MAX = 200


def set_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """把 WS 端点所在的事件循环绑定为投递目标（端点 accept 前调用；传 None 供测试隔离）。"""
    global _loop
    _loop = loop


def subscribe(owner: str) -> asyncio.Queue:
    """为 owner 登记一条投递队列，返回队列供端点 await 取消息。"""
    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers.setdefault(owner, []).append(q)
    return q


def unsubscribe(owner: str, q: asyncio.Queue) -> None:
    queues = _subscribers.get(owner)
    if queues and q in queues:
        queues.remove(q)
        if not queues:
            _subscribers.pop(owner, None)


def publish_event(owner: str, payload: dict) -> None:
    """跨线程投递给该 owner 的所有连接；未绑定 loop / 队列满时静默丢弃。"""
    loop = _loop
    if loop is None or loop.is_closed():
        return

    for q in list(_subscribers.get(owner, [])):
        # 队列满则丢新事件，绝不阻塞 worker 线程
        def _put(q: asyncio.Queue = q) -> None:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

        # worker 线程无权直接操作 loop 内部状态，必须经线程安全入口投递
        loop.call_soon_threadsafe(_put)
