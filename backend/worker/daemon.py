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
        self._start_time = time.time()
        self._status = "initialized"
        self._trades_count = 0
        self._orders_count = 0
        self._last_action = None
        self._last_error = None
        self._last_price = 0.0
        self._strategy_loop = None  # strategy.loop.StrategyLoop 实例（start 命令后非空）
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
                "last_price": self._last_price,
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
            # 幂等：策略已在运行（如编排层重试）时直接返回 ok，不重复
            # 创建 StrategyLoop（否则旧线程泄漏且双 loop 并发回调）
            if self._strategy_loop is not None:
                return make_response(
                    self.worker_id,
                    request_id,
                    STATUS_OK,
                    # status 固定 "running"：loop 存在即运行时在跑，用 self._status
                    # 可能出现 "stopped 但 already_running" 的自相矛盾返回体
                    {"worker_id": self.worker_id, "status": "running", "pid": self.pid, "already_running": True},
                )
            # 真实启动策略运行时（策略加载 + StrategyLoop 线程），失败返回 error
            try:
                self._start_strategy(command.get("params") or {})
            except Exception as e:
                self._last_error = str(e)
                self.logger.exception(f"Worker {self.worker_id} 策略启动失败")
                return make_response(self.worker_id, request_id, STATUS_ERROR, {"error": f"策略启动失败: {e}"})
            self._status = "running"
            self._running = True
            self._last_error = None
            return make_response(
                self.worker_id,
                request_id,
                STATUS_OK,
                {"worker_id": self.worker_id, "status": "running", "pid": self.pid},
            )
        elif cmd == "stop":
            self._stop_strategy()
            self._running = False
            self._status = "stopped"
            return make_response(self.worker_id, request_id, STATUS_OK, {"stopped": True})
        elif cmd == "update_params":
            return make_response(self.worker_id, request_id, STATUS_OK, {"updated": True})
        else:
            # 不实现 restart：编排层（core_service.restart_worker）用
            # stop+start 两跳实现，daemon 无需感知复合命令
            return make_response(self.worker_id, request_id, STATUS_ERROR, {"error": f"Unknown command: {cmd}"})

    def cleanup(self) -> None:
        self._stop_strategy()
        if self._transport:
            self._transport.close()
            self._transport = None

    # ==================== 策略执行内核（独立进程内运行） ====================

    def _start_strategy(self, params: dict[str, Any]) -> None:
        """在 daemon 进程内真实启动策略运行时。

        复用与 FastAPI 进程内 StrategyManager 相同的加载链：
        StrategyLoaderService 加载策略类 → 交易所适配器 → StrategyLoop 线程。
        加载失败时降级为占位策略（不交易），与 StrategyManager 语义一致。

        Args:
            params: start 命令携带的策略配置（strategy_name/symbols/timeframe/
                    strategy_params/trading_mode，由 core_service._build_worker_config 提供）

        ponytail: 命令处理是同步的，策略 import 链约 1-3s 会短暂阻塞事件循环
                  （心跳最多延迟一次）；orchestrator 侧 start 超时 5s，
                  若策略加载未来变慢需改为后台任务 + 两段式响应。
        """
        strategy_name = params.get("strategy_name") or ""
        symbol = (params.get("symbols") or ["BTCUSDT"])[0]
        strategy_params = params.get("strategy_params") or {}
        timeframe = params.get("timeframe") or "1h"
        trading_mode = params.get("trading_mode") or "paper"
        if trading_mode != "paper":
            # trading_mode 已消费并留档：真实 testnet/live adapter 尚未接入，
            # 与 StrategyManager 的语义一致，非 paper 模式暂回退 paper 运行
            self.logger.warning(f"[Daemon] trading_mode={trading_mode} 暂未接入真实适配器，回退 paper 模式")

        # 延迟导入：保持 daemon 初始启动轻量，策略 import 链只在 start 时加载
        try:
            from backtest.strategy_loader_service import StrategyLoaderService
        except Exception as e:  # 策略加载链不可用（如缺依赖）→ 占位假策略，不与真实交易混淆
            self.logger.warning(f"[Daemon] 策略加载器不可用，使用占位策略: {e}")
            StrategyLoaderService = None

        strategy_instance = None
        if StrategyLoaderService is not None:
            try:
                instruments = {symbol: {"symbol": symbol, "venue": "BINANCE"}}
                bar_types = {symbol: timeframe}
                strategy_instance = StrategyLoaderService.load_event_strategy_multi(
                    strategy_name=strategy_name,
                    strategy_params=strategy_params,
                    bar_types=bar_types,
                    instruments=instruments,
                )
            except Exception as e:
                self.logger.warning(f"[Daemon] 策略加载失败，使用占位策略: {e}")

        if strategy_instance is None:
            from backtest.backtest_loop import RuleStrategy

            class _PlaceholderStrategy(RuleStrategy):
                """占位策略：策略加载失败时使用，不会触发任何交易"""

                def on_bar(self, bar: dict) -> Any:
                    from axon_bridge import Action

                    return Action("hold", 0.0, 0.0, "placeholder", 0)

            strategy_instance = _PlaceholderStrategy()

        # 交易所适配器：真实 testnet/live adapter 在后续版本接入，
        # 当前使用零配置 PaperAdapter（与 StrategyManager 的 paper 语义一致）
        adapter = _PaperAdapter(symbol=symbol)
        from strategy.loop import StrategyLoop

        self._strategy_loop = StrategyLoop(
            adapter=adapter,
            strategy=strategy_instance,
            symbol=symbol,
            event_callback=self._emit_strategy_event,
        )
        self._strategy_loop.start()
        self.logger.info(f"[Daemon] 策略已启动: worker_id={self.worker_id}, strategy={strategy_name}, symbol={symbol}")

    def _stop_strategy(self) -> None:
        """停止策略运行时（幂等，进程退出时也会调用）。"""
        if self._strategy_loop is not None:
            try:
                self._strategy_loop.stop()
            except Exception as e:
                self.logger.error(f"[Daemon] 停止策略循环失败: {e}")
            self._strategy_loop = None

    def _emit_strategy_event(self, event_type: str, data: dict[str, Any]) -> None:
        """StrategyLoop 事件回调 → 更新统计 + 转发到 ZMQ 事件通道。

        - order.placed/rejected: 转发给 Orchestrator（前端实时可见）
        - bar.processed: 高频事件不转发，仅更新心跳统计字段（last_price/last_action）
        """
        if event_type == "bar.processed":
            self._last_price = float(data.get("price", 0.0) or 0.0)
            self._last_action = data.get("action")
            return

        z_type = "order" if event_type == "order.placed" else "log"
        if event_type == "order.placed":
            self._orders_count += 1
        if self._transport is not None:
            try:
                self._transport.send_event(make_event(self.worker_id, z_type, {"event": event_type, **data}))
            except Exception as e:
                self.logger.error(f"[Daemon] 事件转发失败 ({event_type}): {e}")

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
            self._stop_strategy()  # 先停策略线程再关 ZMQ，避免线程再向已关闭的 socket 发事件
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


class _PaperAdapter:
    """零配置纸面交易适配器。

    实现 StrategyLoop 约定的接口 connect/disconnect/subscribe/get_ticker/place_order。
    与 StrategyManager._build_exchange_adapter 的 paper 语义一致：
    ponytail: 无真实行情接入，get_ticker 恒返回种子价（策略 on_bar 正常空转、
    决策链可运行但不会产生虚假成交），真实 testnet/live adapter 后续替换本类。
    """

    def __init__(self, symbol: str, seed_price: float = 0.0):
        self._symbol = symbol
        self._seed_price = seed_price
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def subscribe(self, symbols: list[str]) -> None:
        pass

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        # 无行情源：返回种子价。StrategyLoop 对 price<=0 有防御（跳过下单）
        return {"symbol": symbol, "last": self._seed_price}

    def place_order(self, order_dict: dict[str, Any]) -> dict[str, Any]:
        # 纸面模式不下真实单，仅返回记录型回执（event 由 StrategyLoop 回调负责上报）
        return {"paper": True, "symbol": order_dict.get("symbol"), "order_id": ""}


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
