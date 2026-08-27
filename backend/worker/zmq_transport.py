"""ZMQ 传输层: 封装 Worker 端和 Orchestrator 端的 ZMQ 通道。

Worker 端: connect 模式 (PULL 接收命令, PUSH 发送事件)
Orchestrator 端: bind 模式 (PULL 接收事件, DEALER 发送命令按 worker_id 路由)
"""

from __future__ import annotations

import socket
import time
from typing import Any

from .protocol import (
    decode_message,
    encode_message,
)


def _find_free_port() -> int:
    """找到一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class WorkerZmqTransport:
    """Worker 端 ZMQ 传输层: connect 到 Orchestrator。

    命令通道: DEALER (固定 ZMQ_IDENTITY=worker-{id}) → ROUTER 精确路由
    事件通道: PUSH → PULL 单向推送
    """

    def __init__(self, worker_id: int, event_pull_addr: str | None = None, cmd_push_addr: str | None = None):
        import zmq

        self.worker_id = worker_id
        self._ctx = zmq.Context.instance()

        # DEALER 设置固定 identity，ROUTER 端据此精确路由命令
        # 注: ZMQ 中 DEALER 不是路由器，多 PULL 接 DEALER 是 round-robin，
        #     必须用 ROUTER↔DEALER + IDENTITY 才能按 worker 路由
        self.cmd_dealer = self._ctx.socket(zmq.DEALER)
        self.cmd_dealer.setsockopt(zmq.IDENTITY, f"worker-{worker_id}".encode())
        self.cmd_dealer.setsockopt(zmq.RECONNECT_IVL, 100)
        self.cmd_dealer.setsockopt(zmq.RECONNECT_IVL_MAX, 10000)

        self.event_push = self._ctx.socket(zmq.PUSH)
        self.event_push.setsockopt(zmq.RECONNECT_IVL, 100)
        self.event_push.setsockopt(zmq.RECONNECT_IVL_MAX, 10000)

        if event_pull_addr:
            self.event_push.connect(event_pull_addr)
        if cmd_push_addr:
            self.cmd_dealer.connect(cmd_push_addr)
            # 注册帧: ROUTER 只有在收到 DEALER 消息后才会把其 identity
            # 加入路由表。命令是单向的，所以 Worker 必须先主动发一帧。
            self.cmd_dealer.send(b"register")

    def send_event(self, event: dict[str, Any]) -> None:
        """发送事件/心跳/响应。"""
        self.event_push.send(encode_message(event))

    def send_response(self, response: dict[str, Any]) -> None:
        """发送命令响应。"""
        self.event_push.send(encode_message(response))

    def recv_command(self, timeout_ms: int = 5000) -> dict[str, Any] | None:
        """接收命令 (单帧，routing frame 已由 ZMQ 自动剥离)。"""
        import zmq

        self.cmd_dealer.setsockopt(zmq.RCVTIMEO, timeout_ms)
        try:
            raw = self.cmd_dealer.recv()
        except zmq.Again:
            return None
        finally:
            self.cmd_dealer.setsockopt(zmq.RCVTIMEO, -1)
        return decode_message(raw)

    def close(self) -> None:
        try:
            self.cmd_dealer.close(linger=0)
        except Exception:
            pass
        try:
            self.event_push.close(linger=0)
        except Exception:
            pass


class OrchestratorZmqTransport:
    """Orchestrator 端 ZMQ 传输层: bind 等待 Worker 连接。

    命令通道: ROUTER 按 DEALER 的 ZMQ_IDENTITY (worker-{id}) 精确路由
    事件通道: PULL 接收所有 Worker 的 PUSH
    """

    def __init__(self, event_pull_addr: str | None = None, cmd_push_addr: str | None = None):
        import zmq

        self._ctx = zmq.Context.instance()

        self.event_pull = self._ctx.socket(zmq.PULL)
        if event_pull_addr:
            self.event_pull.bind(event_pull_addr)
            self._event_pull_endpoint = event_pull_addr
        else:
            port = _find_free_port()
            self.event_pull.bind(f"tcp://127.0.0.1:{port}")
            self._event_pull_endpoint = f"tcp://127.0.0.1:{port}"

        self.cmd_router = self._ctx.socket(zmq.ROUTER)
        if cmd_push_addr:
            self.cmd_router.bind(cmd_push_addr)
            self._cmd_push_endpoint = cmd_push_addr
        else:
            port = _find_free_port()
            self.cmd_router.bind(f"tcp://127.0.0.1:{port}")
            self._cmd_push_endpoint = f"tcp://127.0.0.1:{port}"

    @property
    def event_pull_endpoint(self) -> str:
        return self._event_pull_endpoint

    @property
    def cmd_push_endpoint(self) -> str:
        return self._cmd_push_endpoint

    def send_command(self, worker_id: int, command: dict[str, Any]) -> None:
        """按 worker identity (worker-{id}) 精确路由命令到指定 Worker。"""
        self._drain_router()
        self.cmd_router.send_multipart(
            [
                f"worker-{worker_id}".encode(),
                encode_message(command),
            ]
        )

    def _drain_router(self) -> None:
        """清空 ROUTER 待处理帧 (注册帧) 以刷新路由表。

        ROUTER 只有在 recv 时才处理 DEALER 发来的消息并记录其 identity
        到路由表。命令是单向的，因此在发命令前必须先 drain 注册帧。
        """
        import zmq

        self.cmd_router.setsockopt(zmq.RCVTIMEO, 10)
        try:
            while True:
                self.cmd_router.recv_multipart()
        except zmq.Again:
            pass
        finally:
            self.cmd_router.setsockopt(zmq.RCVTIMEO, -1)

    def recv_event(self, timeout_ms: int = 100) -> dict[str, Any] | None:
        """接收一个事件/响应 (带超时)。"""
        import zmq

        self.event_pull.setsockopt(zmq.RCVTIMEO, timeout_ms)
        try:
            raw = self.event_pull.recv()
        except zmq.Again:
            return None
        finally:
            self.event_pull.setsockopt(zmq.RCVTIMEO, -1)
        return decode_message(raw)

    def wait_for_response(self, worker_id: int, request_id: str, timeout_ms: int = 5000) -> dict[str, Any] | None:
        """在事件通道上等待指定 Worker 对特定 request_id 的响应。"""
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            remaining_ms = max(100, int((deadline - time.time()) * 1000))
            msg = self.recv_event(timeout_ms=min(remaining_ms, 500))
            if msg is None:
                continue
            if (
                msg.get("type") == "response"
                and msg.get("worker_id") == worker_id
                and msg.get("request_id") == request_id
            ):
                return msg
        return None

    def close(self) -> None:
        try:
            self.event_pull.close(linger=0)
        except Exception:
            pass
        try:
            self.cmd_router.close(linger=0)
        except Exception:
            pass
