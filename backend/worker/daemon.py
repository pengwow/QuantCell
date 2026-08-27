"""Worker 独立进程入口。

每个 Worker 是独立 Python 进程，通过 CLI 启动:
  python -m worker.daemon run --worker-id 11
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from typing import Any

from utils.logger import LogType, get_logger

from .protocol import (
    DEFAULT_CMD_PUSH_ADDR,
    DEFAULT_EVENT_PULL_ADDR,
    STATUS_ERROR,
    STATUS_OK,
    make_event,
    make_response,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Worker 独立进程守护程序")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="运行 Worker")
    run_parser.add_argument("--worker-id", type=int, required=True)
    run_parser.add_argument("--event-pull", default=DEFAULT_EVENT_PULL_ADDR)
    run_parser.add_argument("--cmd-push", default=DEFAULT_CMD_PUSH_ADDR)
    return parser.parse_args(argv)


class WorkerDaemon:
    """Worker 独立进程守护程序。"""

    def __init__(
        self, worker_id: int, event_pull_addr: str = DEFAULT_EVENT_PULL_ADDR, cmd_push_addr: str = DEFAULT_CMD_PUSH_ADDR
    ):
        self.worker_id = worker_id
        self.event_pull_addr = event_pull_addr
        self.cmd_push_addr = cmd_push_addr
        self.pid = os.getpid()
        self._running = False
        self._transport = None
        self._start_time = time.time()
        self._status = "initialized"
        self._trades_count = 0
        self._orders_count = 0
        self._last_action = None
        self._last_error = None
        self.logger = get_logger(f"worker.daemon.{worker_id}", LogType.APPLICATION)
        # 信号只能在主线程注册；本进程作为独立 daemon 由 main() 在主线程构造，
        # 因此在此注册即可（测试同样在主线程构造，与 conftest 的 SIGALRM 不冲突）
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        self.logger.info(f"Worker {self.worker_id} 收到信号 {signum}")
        self._running = False

    def _build_heartbeat(self) -> dict[str, Any]:
        return make_event(
            self.worker_id,
            "heartbeat",
            {
                "pid": self.pid,
                "status": self._status,
                "uptime": time.time() - self._start_time,
                "trades_count": self._trades_count,
                "orders_count": self._orders_count,
                "last_action": self._last_action,
                "last_error": self._last_error,
            },
        )

    def _handle_command(self, command: dict[str, Any]) -> dict[str, Any]:
        cmd = command.get("cmd", "")
        request_id = command.get("request_id", "")

        if cmd == "ping":
            return make_response(self.worker_id, request_id, STATUS_OK, {"pong": True})
        elif cmd == "status":
            return make_response(
                self.worker_id,
                request_id,
                STATUS_OK,
                {
                    "worker_id": self.worker_id,
                    "status": self._status,
                    "pid": self.pid,
                },
            )
        elif cmd == "start":
            self._status = "running"
            self._running = True
            return make_response(
                self.worker_id,
                request_id,
                STATUS_OK,
                {"worker_id": self.worker_id, "status": "running", "pid": self.pid},
            )
        elif cmd == "stop":
            self._running = False
            self._status = "stopped"
            return make_response(self.worker_id, request_id, STATUS_OK, {"stopped": True})
        elif cmd == "restart":
            self._status = "restarting"
            return make_response(self.worker_id, request_id, STATUS_OK, {"restarted": True})
        elif cmd == "update_params":
            return make_response(self.worker_id, request_id, STATUS_OK, {"updated": True})
        else:
            return make_response(self.worker_id, request_id, STATUS_ERROR, {"error": f"Unknown command: {cmd}"})

    def cleanup(self) -> None:
        if self._transport:
            self._transport.close()
            self._transport = None

    async def run(self) -> None:
        """主循环: 启动 ZMQ → 心跳 + 命令处理 → 优雅退出。"""
        # 延迟导入 asyncio 与 zmq_transport：仅在真正运行 daemon 时才需要，
        # 避免在模块导入期（如测试 import worker.daemon）就建立事件循环/拉起 ZMQ。
        import asyncio

        from .zmq_transport import WorkerZmqTransport

        self._transport = WorkerZmqTransport(
            worker_id=self.worker_id,
            event_pull_addr=self.event_pull_addr,
            cmd_push_addr=self.cmd_push_addr,
        )
        self.logger.info(f"Worker {self.worker_id} (PID={self.pid}) 已启动")
        self._transport.send_event(self._build_heartbeat())
        self._running = True
        self._status = "running"

        loop = asyncio.get_running_loop()
        hb_task = loop.create_task(self._heartbeat_loop())
        cmd_task = loop.create_task(self._command_loop())

        try:
            while self._running:
                await asyncio.sleep(0.1)
        finally:
            self._status = "stopped"
            cmd_task.cancel()
            hb_task.cancel()
            try:
                await asyncio.gather(cmd_task, hb_task, return_exceptions=True)
            except Exception:
                pass
            if self._transport:
                self._transport.send_event(self._build_heartbeat())
                self._transport.close()
            self.logger.info(f"Worker {self.worker_id} 已关闭")

    async def _heartbeat_loop(self) -> None:
        import asyncio

        while self._running:
            try:
                if self._transport:
                    self._transport.send_event(self._build_heartbeat())
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5.0)

    async def _command_loop(self) -> None:
        import asyncio

        while self._running:
            try:
                if self._transport:
                    # 500ms 轮询而非长阻塞: recv_command 是同步阻塞调用（RCVTIMEO），
                    # 长超时会让任务取消延迟到该次 recv 超时（此前实测退出需 5s）
                    command = self._transport.recv_command(timeout_ms=500)
                    if command:
                        response = self._handle_command(command)
                        self._transport.send_response(response)
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)


def main() -> None:
    """Worker Daemon 入口。"""
    args = parse_args()
    daemon = WorkerDaemon(
        worker_id=args.worker_id,
        event_pull_addr=args.event_pull,
        cmd_push_addr=args.cmd_push,
    )
    try:
        import asyncio

        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass
    finally:
        daemon.cleanup()


if __name__ == "__main__":
    main()
