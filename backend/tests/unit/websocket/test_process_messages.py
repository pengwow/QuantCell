"""websocket.ConnectionManager.process_messages 消息投递测试。

回归背景: process_messages 曾按"同 topic 只发最新一条"合并,
该优化为高频 K 线行情设计, 但 kline 行情走 lifespan 的直接 broadcast
不经过队列; 而队列里 task:progress 逐条承载子任务状态跳变,
合并导致子任务终值推送丢失, 前端进度卡在中间值。
"""

import asyncio
import contextlib

import pytest

from websocket.manager import ConnectionManager


class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, message: dict):
        self.sent.append(message)


@pytest.mark.asyncio
async def test_process_messages_delivers_all_same_topic_messages():
    """同一 topic 的批量消息必须逐条送达, 不得合并丢弃。"""
    manager = ConnectionManager()
    # 单例可能被其它用例（FastAPI lifespan 启停）启动过消费循环, 先清理避免双消费者分走消息。
    # 残留任务可能绑定在已关闭的旧事件循环上（lifespan shutdown 的 1s 超时内未完成取消）,
    # 跨 loop await 它会抛 RuntimeError: attached to a different loop —— 只能标记取消
    # 并置空指针跳过; 仅当任务属于当前 loop 时才真正等待其退出
    stale = manager.processing_task
    if stale is not None and not stale.done():
        stale.cancel()
        if stale.get_loop() is asyncio.get_running_loop():
            with contextlib.suppress(asyncio.CancelledError):
                await stale
    manager.processing_task = None
    manager.message_queue = asyncio.Queue()
    fake_ws = _FakeWS()
    manager.active_connections = {"c1": fake_ws}
    manager.subscriptions = {"task:progress": {"c1"}}

    consumer = asyncio.create_task(manager.process_messages())
    try:
        for i in range(3):
            await manager.queue_message(
                {"type": "task:progress", "data": {"percent": i}},
                topic="task:progress",
            )
        # 批处理窗口 batch_interval=0.1s, 多留余量
        for _ in range(50):
            await asyncio.sleep(0.02)
            received = [m for m in fake_ws.sent if m.get("type") == "task:progress"]
            if len(received) >= 3:
                break
    finally:
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer

    received = [m for m in fake_ws.sent if m.get("type") == "task:progress"]
    assert [m["data"]["percent"] for m in received] == [0, 1, 2]
