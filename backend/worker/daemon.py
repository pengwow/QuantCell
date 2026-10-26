"""Worker 独立进程入口。

每个 Worker 是独立 Python 进程，通过 CLI 启动:
  python -m worker.daemon run --worker-id 11
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path
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
        self._status = "initialized"
        self.logger = get_logger(f"worker.daemon.{worker_id}", LogType.APPLICATION)
        # 信号只能在主线程注册；本进程作为独立 daemon 由 main() 在主线程构造，
        # 因此在此注册即可（测试同样在主线程构造，与 conftest 的 SIGALRM 不冲突）
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        self.logger.info(f"Worker {self.worker_id} 收到信号 {signum}")
        self._running = False

    def _build_heartbeat(self) -> dict[str, Any]:
        # payload 只带 orchestrator 实际消费的字段（pid/status，见
        # orchestrator._drain_and_process_events）；交易统计走 core_service
        # 独立统计链路，不属于心跳
        return make_event(
            self.worker_id,
            "heartbeat",
            {"pid": self.pid, "status": self._status},
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
            # 规则/LLM/RL 统一由进程内 Driver 路径运行（strategy_manager），
            # daemon 不再承载策略执行；stop/status 保留供编排清理与查询
            return make_response(
                self.worker_id,
                request_id,
                STATUS_ERROR,
                {"error": "规则/LLM/RL 统一由进程内 Driver 路径运行，daemon 不再承载策略执行"},
            )
        elif cmd == "stop":
            self._running = False
            self._status = "stopped"
            return make_response(self.worker_id, request_id, STATUS_OK, {"stopped": True})
        elif cmd == "update_params":
            # 动态更新策略参数尚未实现（当前占位策略/paper adapter 无参数可更新）。
            # 明确返回 error 而非伪成功，避免 CLI/前端误以为参数已生效。
            return make_response(self.worker_id, request_id, STATUS_ERROR, {"error": "update_params 尚未实现"})
        else:
            # 不实现 restart：编排层（core_service.restart_worker）用
            # stop+start 两跳实现，daemon 无需感知复合命令
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
        reg_task = loop.create_task(self._register_loop())

        try:
            while self._running:
                await asyncio.sleep(0.1)
        finally:
            self._status = "stopped"
            cmd_task.cancel()
            hb_task.cancel()
            reg_task.cancel()
            try:
                await asyncio.gather(cmd_task, hb_task, reg_task, return_exceptions=True)
            except Exception:
                pass
            if self._transport:
                self._transport.send_event(self._build_heartbeat())
                self._transport.close()
            self.logger.info(f"Worker {self.worker_id} 已关闭")

    async def _register_loop(self) -> None:
        """周期性重发 register 帧。

        ROUTER 只有在收到 DEALER 消息后才会把其 identity 加入路由表。
        CLI 每个命令都是独立进程（ROUTER 随进程销毁/重建），daemon 重连到
        新 ROUTER 时路由表是空的。前 5 次发送用 200ms 短间隔快速补位（命中
        Orchestrator start_worker_process 里 10s 等待窗口），后续降为 2s。
        相比 monitor 事件驱动，定时重发不依赖 ZMQ monitor 语义，简单可靠。
        """
        import asyncio

        attempt = 0
        while self._running:
            try:
                if self._transport:
                    self._transport.send_register()
                # 前 5 次快速发送，让新进程的 ROUTER 迅速获得路由信息
                if attempt < 5:
                    await asyncio.sleep(0.2)
                    attempt += 1
                else:
                    await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break
            except Exception:
                if attempt < 5:
                    await asyncio.sleep(0.2)
                    attempt += 1
                else:
                    await asyncio.sleep(2.0)

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
    # 防御：CLI/API 可能在任意 cwd 下 Popen daemon。daemon.py 位于
    # backend/worker/，把 backend 根加入 sys.path 保证 utils/backtest/strategy
    # 等顶层包始终可导入（daemon 顶部 import utils.logger 也需要它）。
    backend_root = str(Path(__file__).resolve().parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

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
