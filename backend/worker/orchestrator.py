"""Worker 编排器: 管理 Worker 进程的生命周期和 ZMQ 通信。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
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
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def check_health(self) -> dict[str, Any]:
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
        # 发送前确保路由就绪（重连场景），并与响应等待共享同一时间预算
        deadline = time.time() + timeout
        if not self._ensure_worker_routable(worker_id, deadline=deadline):
            self._logger.warning(f"[Orchestrator] Worker {worker_id} 未注册，命令 {cmd} 无法路由")
            return None
        remaining_ms = int((deadline - time.time()) * 1000)
        if remaining_ms <= 0:
            self._logger.warning(f"[Orchestrator] 命令 {cmd} 超时 (Worker {worker_id})")
            return None
        self._transport.send_command(worker_id, command)
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
