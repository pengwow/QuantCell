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
        # 重连上限压到 1s：CLI 每次都是独立进程，ROUTER 随进程反复销毁/重建，
        # 若退避到默认的数十秒，daemon 重连到新 ROUTER 会过慢，status/stop 探测超时
        self.cmd_dealer.setsockopt(zmq.RECONNECT_IVL_MAX, 1000)

        self.event_push = self._ctx.socket(zmq.PUSH)
        self.event_push.setsockopt(zmq.RECONNECT_IVL, 100)
        # 与 cmd_dealer 同理：命令响应走 event_push，重连上限过大时，
        # stop 响应会在 CLI 进程切换后迟迟发不回来，导致命令超时
        self.event_push.setsockopt(zmq.RECONNECT_IVL_MAX, 1000)

        if event_pull_addr:
            self.event_push.connect(event_pull_addr)
        if cmd_push_addr:
            self.cmd_dealer.connect(cmd_push_addr)
            # DONTWAIT：若 ROUTER 尚未 bind 或对端端列已满，立即抛 ZMQError
            # 而不是在 send 队列里无限排队等待，让上层 _register_loop 接手重试。
            # 曾观察到：ROUTER bind 延迟数十毫秒，register 帧在 ZMQ 内部排队、
            # 但 _wait_for_worker_registration 还没开始等，导致消费窗口错过。
            try:
                self.cmd_dealer.send(b"register", zmq.DONTWAIT)  # type: ignore[attr-defined]
            except zmq.ZMQError as e:
                # 帧未送达（对端未就绪/队列已满），留给周期重发。
                logger = self._get_internal_logger()
                logger.debug(f"[WorkerZmqTransport] 首次 register 未送达 (DONTWAIT): {e}")

    def _get_internal_logger(self):
        """最小依赖的内置日志获取。

        本模块为传输层，不在顶部 import utils.logger 以避免在非 daemon 场景
        （如单元测试只导入 transport，日志系统未初始化）下触发副作用。
        """
        import logging

        return logging.getLogger("worker.zmq_transport")

    def send_register(self) -> None:
        """发送 register 帧（幂等）。

        ROUTER 收到后会把 worker-{id} 加入路由表；重复发送无副作用。
        daemon 定期调用本方法，保证 CLI 新进程的 ROUTER 能获得路由信息。
        注: 曾尝试用 ZMQ monitor 的事件驱动重发，但 monitor 端点基于 fd，
        fd 复用会串事件且解析依赖平台字节序，复杂度高收益低，弃用。
        """
        import zmq

        try:
            self.cmd_dealer.send(b"register")
        except zmq.ZMQError:
            pass

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
            # 给短暂 linger 让已入队的 response/heartbeat 帧 flush 到对端，
            # 否则 daemon 收到 stop 后立即退出会丢弃 response，导致
            # orchestrator 傻等命令超时后才走 SIGTERM 兜底
            self.event_push.close(linger=500)
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

        # 孤儿响应缓存：并发命令时乱序到达的"别人的响应"暂存于此，
        # 由对应 request_id 的 wait_for_response 领取（并发互吞问题的解药）
        self._orphan_responses: dict[str, dict[str, Any]] = {}

    @property
    def event_pull_endpoint(self) -> str:
        return self._event_pull_endpoint

    @property
    def cmd_push_endpoint(self) -> str:
        return self._cmd_push_endpoint

    def send_command(
        self,
        worker_id: int,
        command: dict[str, Any],
        on_identity_seen: Any | None = None,
        deadline: float | None = None,
    ) -> bool:
        """按 worker identity (worker-{id}) 精确路由命令到指定 Worker。

        Args:
            worker_id: 目标 Worker ID
            command: 命令消息体
            on_identity_seen: 可选回调 `fn(worker_id:int)->None`，
                              每次收到 register 帧时触发，用于外部注册表更新。
            deadline: 可选绝对秒级 deadline（time.time() 尺度）。

        Returns:
            bool: 是否确认目标 identity 已进入 ROUTER 路由表后发出命令。
                  False 表示目标 register 在 deadline 内未到达，命令未发出。

        旧实现：每次调用 _drain_router 无差别清空 cmd_router，在多 Worker
        并行启动场景下会清掉"其他 Worker 的 register 帧"，导致其他 Worker
        后续命令路由偶现失败。
        新实现：用 zmq.Poller 逐帧消费，对每个 register 帧更新注册表（通过
        on_identity_seen 回调回填），只消费到目标 identity 出现为止；其他
        Worker 的 register 都会被正确登记，不会丢失。
        """
        import zmq

        target_identity = f"worker-{worker_id}".encode()

        end_ts = deadline if deadline is not None else (time.time() + 0.1)  # 默认 100ms
        poller = zmq.Poller()
        poller.register(self.cmd_router, zmq.POLLIN)
        self.cmd_router.setsockopt(zmq.RCVTIMEO, 10)
        target_ready = False
        try:
            while time.time() < end_ts:
                remain_ms = max(1, int((end_ts - time.time()) * 1000))
                ready = dict(poller.poll(timeout=min(remain_ms, 20)))
                if self.cmd_router not in ready:
                    continue
                try:
                    frames = self.cmd_router.recv_multipart()
                except zmq.Again:
                    continue
                if not frames:
                    continue
                identity = frames[0]
                try:
                    wid = int(identity.decode().removeprefix("worker-"))
                except UnicodeDecodeError, ValueError:
                    continue
                if on_identity_seen is not None:
                    try:
                        on_identity_seen(wid)
                    except Exception:
                        pass
                if identity == target_identity:
                    target_ready = True
                    break
        finally:
            self.cmd_router.setsockopt(zmq.RCVTIMEO, -1)
            poller.unregister(self.cmd_router)

        if not target_ready:
            # ROUTER_MANDATORY 默认 0：未知 identity 的消息会被静默丢弃。
            # 未确认路由就绪时不发送，避免下游误认为命令已送达。
            return False
        self.cmd_router.send_multipart([target_identity, encode_message(command)])
        return True

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
        """在事件通道上等待指定 Worker 对特定 request_id 的响应。

        并发正确性：多个命令并发等待时，A 的 wait 可能先收到 B 的响应。
        不匹配的响应不再丢弃，而是存入 _orphan_responses 缓存（按 request_id
        索引），B 的 wait 每轮先查缓存命中即返回——响应不会因乱序被误吞，
        避免等待方假超时（超时对 start 命令意味着 kill 已启动的 Worker）。
        """
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            # 先查孤儿缓存（其他等待者替我们收到的响应）
            cached = self._orphan_responses.pop(request_id, None)
            if cached is not None:
                if time.time() - cached.get("_ts", 0) > 60:
                    continue  # 过期残留，跳过
                return cached
            remaining_ms = max(100, int((deadline - time.time()) * 1000))
            msg = self.recv_event(timeout_ms=min(remaining_ms, 500))
            if msg is None:
                continue
            if msg.get("type") != "response":
                continue  # 心跳/事件混入（理论上不会，防御性跳过）
            if msg.get("worker_id") == worker_id and msg.get("request_id") == request_id:
                return msg
            # 别人的响应：存入缓存供对应等待者领取，而非丢弃
            req_id = msg.get("request_id")
            if req_id and req_id not in self._orphan_responses:
                msg["_ts"] = time.time()
                self._orphan_responses[req_id] = msg
        return None

    def store_orphan_response(self, msg: dict[str, Any]) -> None:
        """把非命令等待期间收到的响应存入孤儿缓存（供 wait_for_response 领取）。"""
        req_id = msg.get("request_id")
        if req_id:
            msg["_ts"] = time.time()
            self._orphan_responses[req_id] = msg

    def close(self) -> None:
        try:
            self.event_pull.close(linger=0)
        except Exception:
            pass
        try:
            self.cmd_router.close(linger=0)
        except Exception:
            pass
