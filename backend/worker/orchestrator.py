"""Worker 编排器: 管理 Worker 进程的生命周期和 ZMQ 通信。"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.logger import LogType, get_logger

from .config import ZmqConfig
from .protocol import (
    STATUS_ERROR,
    STATUS_OK,
    make_command,
)


@dataclass
class WorkerConnectionInfo:
    """Worker 连接信息。"""

    worker_id: int
    pid: int | None = None
    connected: bool = False
    last_heartbeat: float = 0.0
    status: str = "unknown"
    error_message: str | None = None

    @property
    def is_alive(self) -> bool:
        return self.connected and (time.time() - self.last_heartbeat) < 60.0


class WorkerOrchestrator:
    """Worker 编排器 (单例，与 WorkerCoreService 相同的 __new__ 模式)。"""

    _instance: WorkerOrchestrator | None = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: ZmqConfig | None = None):
        if self._initialized:
            return
        self.config = config or ZmqConfig()
        self._registry: dict[int, WorkerConnectionInfo] = {}
        self._running = False
        self._transport = None
        # event_pull 的互斥：wait_for_response（命令期）与 check_health 的
        # drain 共享同一个 PULL socket，必须串行消费，否则响应会被 drain 误吞
        self._event_lock = threading.Lock()
        self._external_events: list[tuple[int | None, str, dict]] = []
        self._logger = get_logger("worker.orchestrator", LogType.APPLICATION)
        self._initialized = True

    @classmethod
    def get_instance(cls) -> WorkerOrchestrator:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def start_worker_process(self, worker_id: int) -> int:
        """通过 subprocess 启动 Worker 独立进程。"""
        # 先确保 transport 已 bind：否则 daemon 在端点未就绪时 connect，
        # register 帧会排队无法及时到达 router，后续命令将被 ROUTER 丢弃
        self.ensure_transport()
        cmd = [
            sys.executable,
            "-m",
            "worker.daemon",
            "run",
            "--worker-id",
            str(worker_id),
            "--event-pull",
            self.config.event_pull_addr,
            "--cmd-push",
            self.config.cmd_push_addr,
        ]
        self._logger.info(f"[Orchestrator] 启动 Worker {worker_id}: {' '.join(cmd)}")
        # cwd 锚定 backend 根：`-m worker.daemon` 的模块查找发生在 daemon 代码
        # 执行之前，若 CLI/API 从其他目录启动，worker 包不在 sys.path 会直接
        # ModuleNotFoundError（daemon main() 内的 sys.path 防御救不了 -m 阶段）。
        backend_root = str(Path(__file__).resolve().parent.parent)
        proc = subprocess.Popen(cmd, cwd=backend_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pid = proc.pid
        # 等待 daemon 完成 ZMQ 注册（register 帧到达 router），而非固定
        # sleep 0.5s：daemon 启动需 import 大量模块，固定睡眠会错过注册帧
        if not self._wait_for_worker_registration(worker_id):
            # daemon 未在超时内注册（可能启动崩溃），终止进程避免残留孤儿进程
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            raise RuntimeError(f"Worker {worker_id} 未在超时内完成 ZMQ 注册")
        self._register_worker(worker_id, pid=pid)
        self._logger.info(f"[Orchestrator] Worker {worker_id} 已启动, PID={pid}")
        return pid

    def _wait_for_worker_registration(
        self, worker_id: int, timeout: float = 10.0, deadline: float | None = None
    ) -> bool:
        """等待 Worker 的 register 帧到达 router，确保路由表就绪。

        daemon 启动后 DEALER 会 connect 并发送裸 register 帧，ROUTER 只有
        recv 到该帧才会把 worker-{id} 加入路由表。命令是单向的，因此必须
        在发送命令前先消费掉这次注册帧，否则命令会被 ROUTER 丢弃。
        """
        import zmq

        end = deadline if deadline is not None else time.time() + timeout
        target = f"worker-{worker_id}".encode()
        self._transport.cmd_router.setsockopt(zmq.RCVTIMEO, 100)
        try:
            while time.time() < end:
                try:
                    frames = self._transport.cmd_router.recv_multipart()
                except zmq.Again:
                    continue
                if frames and frames[0] == target:
                    return True
            return False
        finally:
            self._transport.cmd_router.setsockopt(zmq.RCVTIMEO, -1)

    def _ensure_worker_routable(self, worker_id: int, deadline: float) -> bool:
        """发送命令前确保目标 Worker 已进入 router 路由表。

        本进程内已注册（start 路径已消费过 register）则直接返回；否则是
        CLI 独立进程探测已运行的 daemon，需等 daemon 重连到本进程新 bind
        的 ROUTER 后重发的 register 帧到达，否则命令会被 ROUTER 丢弃。
        """
        info = self._registry.get(worker_id)
        if info is not None and info.connected:
            return True
        return self._wait_for_worker_registration(worker_id, deadline=deadline)

    def stop_worker_process(self, worker_id: int, timeout: float = 10.0) -> bool:
        """停止 Worker 进程: 先发 stop 命令，超时则 kill。"""
        self._logger.info(f"[Orchestrator] 停止 Worker {worker_id}")
        if self.is_connected(worker_id):
            try:
                response = self.send_command_and_wait(worker_id, "stop", {}, timeout=timeout)
                if response and response.get("status") == STATUS_OK:
                    self._unregister_worker(worker_id)
                    return True
            except Exception as e:
                self._logger.warning(f"[Orchestrator] Worker {worker_id} 优雅停止失败: {e}")

        info = self._registry.get(worker_id)
        if info and info.pid:
            try:
                os.kill(info.pid, 15)
                time.sleep(2)
                try:
                    pid, _ = os.waitpid(info.pid, os.WNOHANG)
                    if pid == 0:
                        os.kill(info.pid, 9)
                except OSError, ChildProcessError:
                    pass
            except ProcessLookupError:
                pass
        self._unregister_worker(worker_id)
        return True

    def kill_worker_process(self, worker_id: int) -> bool:
        """强制终止 Worker 进程。"""
        info = self._registry.get(worker_id)
        if not info or not info.pid:
            return False
        try:
            os.kill(info.pid, 9)
        except ProcessLookupError:
            pass
        self._unregister_worker(worker_id)
        return True

    def _register_worker(self, worker_id: int, pid: int | None = None) -> None:
        self._registry[worker_id] = WorkerConnectionInfo(
            worker_id=worker_id,
            pid=pid,
            connected=True,
            last_heartbeat=time.time(),
            status="running",
        )

    def _unregister_worker(self, worker_id: int) -> None:
        if worker_id in self._registry:
            self._registry[worker_id].connected = False
            self._registry[worker_id].status = "stopped"

    def _update_heartbeat(self, worker_id: int) -> None:
        if worker_id in self._registry:
            self._registry[worker_id].last_heartbeat = time.time()

    def is_connected(self, worker_id: int) -> bool:
        info = self._registry.get(worker_id)
        return info is not None and info.connected and info.is_alive

    def get_worker_info(self, worker_id: int) -> WorkerConnectionInfo | None:
        return self._registry.get(worker_id)

    def list_connected_workers(self) -> list[dict[str, Any]]:
        return [
            {"worker_id": wid, "pid": info.pid, "status": info.status}
            for wid, info in self._registry.items()
            if info.connected and info.is_alive
        ]

    def _get_disconnected_workers(self) -> list[int]:
        return [wid for wid, info in self._registry.items() if info.connected and not info.is_alive]

    # ==================== 事件消费（PULL 通道 drain） ====================

    def _drain_and_process_events(self) -> None:
        """drain 事件通道积压，回填心跳、暂存外部事件。

        前因：FastAPI 空闲期无人 recv event_pull，heartbeat 事件在 PULL 队列
        堆积（HWM 1000 后被丢），last_heartbeat 停摆 → 60s 误判离线。
        本方法在每次 check_health 时清空积压：heartbeat 直接回填注册表，
        order/log 等外部事件存入 _external_events 供 lifespan 广播。

        与 wait_for_response 的并发互斥由 _event_lock 保证：命令等待期间
        不 drain，避免响应被误消费后命令假超时。
        """
        if self._transport is None:
            return
        with self._event_lock:
            while True:
                try:
                    msg = self._transport.recv_event(timeout_ms=20)
                except Exception as e:
                    self._logger.debug(f"[Orchestrator] 事件 drain 异常: {e}")
                    break
                if msg is None:
                    break
                if msg.get("type") == "response":
                    # 并发命令的响应可能落在 drain 窗口：存入孤儿缓存供对应
                    # wait_for_response 领取，不丢弃（避免并发命令假超时误杀）
                    self._transport.store_orphan_response(msg)
                    continue
                worker_id = msg.get("worker_id")
                event_type = msg.get("event_type")
                payload = msg.get("payload") or {}
                if event_type == "heartbeat" and worker_id is not None:
                    if payload.get("status") == "stopped":
                        # daemon 停前最后一拍：直接标记离线，避免 60s 内
                        # 显示 "stopped 但 connected" 的矛盾中间态
                        self._unregister_worker(worker_id)
                        continue
                    info = self._registry.get(worker_id)
                    if info is None:
                        info = WorkerConnectionInfo(worker_id=worker_id)
                        self._registry[worker_id] = info
                    info.connected = True
                    info.last_heartbeat = time.time()
                    info.pid = payload.get("pid") or info.pid
                    info.status = payload.get("status") or info.status
                else:
                    self._external_events.append((worker_id, event_type, payload))

    def pop_external_events(self) -> list[tuple[int | None, str, dict]]:
        """取出 drain 期间收集的外部事件（order/log 等）并清空。"""
        with self._event_lock:
            events = list(self._external_events)
            self._external_events.clear()
            return events

    def check_health(self) -> dict[str, Any]:
        self._drain_and_process_events()
        disconnected = self._get_disconnected_workers()
        if disconnected:
            self._logger.warning(f"[健康检查] {len(disconnected)} 个 Worker 已断开: {disconnected}")
            for wid in disconnected:
                self._unregister_worker(wid)
        return {
            "total": len(self._registry),
            "connected": len(self._registry) - len(disconnected),
            "disconnected": len(disconnected),
            "disconnected_ids": disconnected,
            "timestamp": time.time(),
        }

    def send_command_and_wait(
        self, worker_id: int, cmd: str, params: dict[str, Any] | None = None, timeout: float | None = None
    ) -> dict[str, Any] | None:
        timeout = timeout or self.config.cmd_timeout
        command = make_command(worker_id, cmd, params)
        if not self._transport:
            self._transport = self._create_transport()
        # 总 deadline = 当前时间 + timeout，在 ensure_routable → send_command
        # → wait_for_response 三阶段共享，避免累计等待远超用户预期
        deadline = time.time() + timeout

        # 1) 显式 routable 探测：预算封顶为总超时的 40%（0.3s~2s）。
        #    此前把整个 deadline 传给探测，CLI 探测场景可能在等待 register 帧
        #    时耗尽全部预算，导致随后的命令发送/响应窗口归零而超时误杀。
        routable_budget = min(2.0, max(0.3, timeout * 0.4))
        routable_deadline = min(deadline, time.time() + routable_budget)
        if not self._ensure_worker_routable(worker_id, deadline=routable_deadline):
            # 未探测到，但 send_command 内部还会做一轮 poller 消费，
            # 此时仍有机会命中，因此不直接返回——留给下面的 send_command 自行判定
            pass

        # 2) 发送命令：把剩余 budget 传给 send_command，它会消费 register
        #    帧并回调 _on_identity_seen 更新注册表 connected 状态
        remaining = max(0.001, deadline - time.time())

        def _on_id(wid: int) -> None:
            # 消费到 register 帧时立刻回填注册表，不走 _wait_for_worker_registration
            # 的"等目标帧"逻辑；这样非目标 Worker 的 register 也不会丢失
            info = self._registry.get(wid)
            ts = time.time()
            if info is not None:
                info.connected = True
                info.last_heartbeat = ts
            else:
                self._registry[wid] = WorkerConnectionInfo(
                    worker_id=wid, connected=True, last_heartbeat=ts, status="unknown"
                )

        send_deadline = time.time() + min(remaining, max(0.05, remaining))
        sent = self._transport.send_command(
            worker_id,
            command,
            on_identity_seen=_on_id,
            deadline=send_deadline,
        )
        if not sent:
            self._logger.warning(f"[Orchestrator] Worker {worker_id} 路由未就绪，命令 {cmd} 已丢弃（未发送）")
            return None

        remaining_ms = int((deadline - time.time()) * 1000)
        if remaining_ms <= 0:
            self._logger.warning(f"[Orchestrator] 命令 {cmd} 超时 (Worker {worker_id})")
            return None
        # 持锁等待响应：与 check_health 的 drain 互斥，防止本轮响应被 drain 吞掉
        with self._event_lock:
            response = self._transport.wait_for_response(
                worker_id,
                command["request_id"],
                timeout_ms=remaining_ms,
            )
        if response:
            self._update_heartbeat(worker_id)
            if cmd == "status" and "data" in response:
                data = response["data"]
                info = self._registry.get(worker_id)
                if info and "status" in data:
                    info.status = data["status"]
        else:
            self._logger.warning(f"[Orchestrator] 命令 {cmd} 超时 (Worker {worker_id})")
        return response

    def send_command_no_wait(self, worker_id: int, cmd: str, params: dict[str, Any] | None = None) -> None:
        command = make_command(worker_id, cmd, params)
        if not self._transport:
            self._transport = self._create_transport()
        # no-wait 版本：不等待身份、不报错；如果目标未注册，send_command
        # 返回 False 时也不处理（fire-and-forget 语义）
        self._transport.send_command(worker_id, command)

    def _create_transport(self):
        from .zmq_transport import OrchestratorZmqTransport

        self._logger.info("[Orchestrator] 创建 ZMQ 传输层")
        return OrchestratorZmqTransport(
            event_pull_addr=self.config.event_pull_addr,
            cmd_push_addr=self.config.cmd_push_addr,
        )

    def ensure_transport(self):
        if self._transport is None:
            self._transport = self._create_transport()
        return self._transport

    def cleanup(self) -> None:
        self._running = False
        if self._transport:
            self._transport.close()
            self._transport = None
        self._registry.clear()
