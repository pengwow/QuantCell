"""
Worker System — NautilusTradingSystem 策略执行引擎

基于 asyncio 单进程架构的策略生命周期管理引擎，替代原来的多进程 WorkerSystem。

职责:
    - 策略生命周期管理（创建、启动、停止、删除）
    - NautilusTrader TradingNode 的构建与异步运行
    - 回测执行
    - 启动时从数据库恢复策略状态
    - 三层策略管理：全局单例 + 内存注册表 + 数据库持久化

注意:
    - 不使用 multiprocessing 进程隔离
    - 不使用 ZMQ 进行 IPC 通信
    - 所有策略作为 asyncio 后台任务在同一事件循环中运行
"""


import asyncio
import json
import os
import signal
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.db_session import get_db_session
from utils.logger import get_logger, LogType

from . import crud
from .config import build_trading_node_config, NAUTILUS_AVAILABLE, NAUTILUS_MISSING_DETAIL
from .exceptions import (
    WorkerNotFoundException,
    WorkerAlreadyRunningException,
    WorkerNotRunningException,
    WorkerStartFailedException,
)
from .worker_state import WorkerState, worker_state_manager, WorkerStateManager

logger = get_logger(__name__, LogType.APPLICATION)

if NAUTILUS_AVAILABLE:
    try:
        from nautilus_trader.live.node import TradingNode
        from nautilus_trader.common.component import flush_logger
    except ImportError as e:
        TradingNode = None
        flush_logger = None
        NAUTILUS_AVAILABLE = False
        NAUTILUS_MISSING_DETAIL = (
            f"nautilus_trader.live.node 模块不可用 (TradingNode): {e}"
        )
        logger.warning(
            f"[NautilusTradingSystem] NautilusTrader 核心交易模块导入失败，"
            f"策略管理功能受限: {e}"
        )
else:
    TradingNode = None
    flush_logger = None

# =========================================================================
# Monkey-patch NautilusKernel._setup_loop() 阻止覆盖 uvicorn 的 SIGINT 处理器
#
# 根因：TradingNode 在主线程创建时，NautilusKernel._setup_loop() 会调用
#   signal.signal(SIGINT, SIG_DFL) 全局重置 SIGINT 处理器，
#   并在 uvicorn 主事件循环上注册 nautilus 自己的信号处理回调。
#   这导致 uvicorn 再也收不到 Ctrl+C，lifespan shutdown 永不被触发。
#
# 解决：将 _setup_loop() 改为 no-op，因为：
#   - TradingNode 运行在 daemon 线程中，不需要独立信号处理
#   - Ctrl+C 由 uvicorn 默认处理器处理 → lifespan shutdown → 进程退出
#   - daemon 线程随进程退出自动回收
# =========================================================================

_original_setup_loop = None

if TradingNode is not None:
    try:
        from nautilus_trader.system.kernel import NautilusKernel

        _original_setup_loop = NautilusKernel._setup_loop

        def _patched_setup_loop(self):
            """
            完全 no-op：阻止 nautilus_trader 覆盖 SIGINT 处理器

            独立循环模式：每个 TradingNode 使用独立 asyncio 事件循环（daemon 线程）。
            - signal.signal(SIGINT, SIG_DFL) 会全局覆盖 uvicorn 的处理器 → 必须阻止
            - add_signal_handler 会覆盖 wakeup FD（进程全局），使 uvicorn 收不到信号 → 必须阻止
            - 独立循环的 daemon 线程不需要信号处理（CTRL+C 由 uvicorn 主循环处理）
            """
            if self._loop is None:
                return
            if self._loop.is_closed():
                return
            self._log.debug(
                "信号处理跳过（独立循环模式，由 uvicorn 主循环处理信号）"
            )

        NautilusKernel._setup_loop = _patched_setup_loop
        logger.info(
            "[NautilusTradingSystem] 已 patch NautilusKernel._setup_loop() "
            "(独立循环模式: 阻止 SIG_DFL 覆盖, 允许独立循环注册信号)"
        )
    except ImportError:
        logger.warning(
            "[NautilusTradingSystem] 无法导入 NautilusKernel, 跳过 signal handler patch"
        )


class NautilusTradingSystem:
    """
    NautilusTrader 策略执行引擎（单例）

    作为整个 Worker 模块的核心，管理所有策略的完整生命周期。
    运行在 asyncio 事件循环中，不创建子进程。

    架构层次:
        1. 全局单例层: 由 state.py 统一持有单例引用
        2. 内存存储层: StrategyRegistry 字典（worker_id → StrategyRuntime）
        3. 数据库持久化层: crud.py 操作 SQLite
    """

    def __init__(self, max_workers: Optional[int] = None):
        self._lock = asyncio.Lock()
        self._initialized = False
        
        # 线程池大小：优先使用配置值，否则根据 CPU 核心数自适应
        if max_workers is None:
            cpu_count = os.cpu_count() or 4
            # 回测任务是 CPU 密集型，线程数不宜超过 CPU 核心数
            max_workers = min(cpu_count, 8)
        
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="nautilus-backtest",
        )
        logger.info(f"[NautilusTradingSystem] ThreadPoolExecutor 初始化: max_workers={max_workers}")

    async def initialize(self) -> None:
        """初始化系统，从数据库恢复策略状态"""
        async with self._lock:
            if self._initialized:
                return
            self._initialized = True

        logger.info("[NautilusTradingSystem] 正在初始化...")

        await worker_state_manager.initialize()

        if not NAUTILUS_AVAILABLE:
            logger.warning("[NautilusTradingSystem] NautilusTrader 不可用，策略管理功能受限")

            if NAUTILUS_MISSING_DETAIL:
                logger.warning(f"[NautilusTradingSystem] 失败原因: {NAUTILUS_MISSING_DETAIL}")

            try:
                import importlib.util
                spec = importlib.util.find_spec("nautilus_trader")
                if spec is None:
                    logger.warning(
                        "[NautilusTradingSystem] 未检测到 nautilus_trader 包，"
                        "请运行 `uv pip install nautilus-trader` 安装"
                    )
                elif spec.origin:
                    logger.info(
                        f"[NautilusTradingSystem] nautilus_trader 包位置: {spec.origin}"
                    )
            except Exception:
                pass

            return

        await self._load_workers_from_db()

        logger.info("[NautilusTradingSystem] 初始化完成")

    async def _load_workers_from_db(self) -> None:
        """从数据库加载 worker 配置到内存注册表"""
        from .state import strategy_registry, StrategyRuntime

        with get_db_session() as db:
            workers, total = crud.get_workers(db, skip=0, limit=1000)
            logger.info(f"[NautilusTradingSystem] 从数据库加载了 {total} 个策略配置")

            for worker in workers:
                runtime = StrategyRuntime(
                    worker_id=worker.id,
                    strategy_id=worker.strategy_id,
                    name=worker.name or f"worker-{worker.id}",
                    status=worker.status or "stopped",
                )
                strategy_registry.register(runtime)

                if worker.status == "running":
                    logger.info(
                        f"[NautilusTradingSystem] 恢复启动运行中的策略: "
                        f"worker_id={worker.id}, name={worker.name}"
                    )
                    try:
                        await self._do_start_strategy(worker.id, worker)
                    except Exception as e:
                        logger.error(
                            f"[NautilusTradingSystem] 恢复启动策略失败: "
                            f"worker_id={worker.id}, error={e}"
                        )
                        strategy_registry.update_status(
                            worker.id, "error", error_message=str(e)
                        )

    async def create_strategy(self, db, worker_config: Dict[str, Any]) -> int:
        """
        创建策略

        Args:
            db: 数据库会话
            worker_config: 策略配置字典

        Returns:
            worker_id
        """
        if not NAUTILUS_AVAILABLE:
            raise RuntimeError("NautilusTrader 不可用，无法创建策略")

        from .state import strategy_registry, StrategyRuntime

        worker = crud.create_worker(db, worker_config)
        db.commit()

        runtime = StrategyRuntime(
            worker_id=worker.id,
            strategy_id=worker.strategy_id,
            name=worker.name or f"worker-{worker.id}",
            status="stopped",
        )
        strategy_registry.register(runtime)

        await worker_state_manager.transition(worker.id, "stopped")

        logger.info(
            f"[NautilusTradingSystem] 策略已创建: worker_id={worker.id}, "
            f"name={worker.name}"
        )
        return worker.id

    async def start_strategy(self, worker_id: int) -> bool:
        """
        启动策略

        Args:
            worker_id: Worker ID

        Returns:
            是否启动成功
        """
        if not NAUTILUS_AVAILABLE:
            logger.warning("[NautilusTradingSystem] NautilusTrader 不可用，无法启动策略")
            return False

        try:
            with get_db_session() as db:
                worker = crud.get_worker(db, worker_id)
                if worker is None:
                    raise WorkerNotFoundException(worker_id)

                await worker_state_manager.transition(worker_id, "starting")
                return await self._do_start_strategy(worker_id, worker, db)
        except WorkerNotFoundException as e:
            logger.warning(f"[NautilusTradingSystem] {e.message}")
            return False
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 启动策略失败: worker_id={worker_id}, "
                f"error={e}\n{traceback.format_exc()}"
            )
            await worker_state_manager.transition(
                worker_id, "error", error_message=str(e)
            )
            return False

    async def _do_start_strategy(self, worker_id: int, worker, db=None) -> bool:
        """
        实际执行策略启动操作

        构建 TradingNode → 注册策略 → 创建 asyncio Task 运行

        Args:
            worker_id: Worker ID
            worker: Worker ORM 对象
            db: 数据库会话（可选）

        Returns:
            是否启动成功
        """
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            logger.warning(
                f"[NautilusTradingSystem] Worker {worker_id} 不在注册表中"
            )
            return False

        if runtime.is_running:
            raise WorkerAlreadyRunningException(worker_id)

        # 构建 TradingNode 配置
        exchange = getattr(worker, 'exchange', 'binance') or 'binance'
        if hasattr(exchange, 'value'):
            exchange = exchange.value

        account_type = getattr(worker, 'account_type', 'spot') or 'spot'
        if hasattr(account_type, 'value'):
            account_type = account_type.value

        trading_mode = getattr(worker, 'trading_mode', 'testnet') or 'testnet'
        if hasattr(trading_mode, 'value'):
            trading_mode = trading_mode.value

        trader_id = f"WORKER-{worker_id:04d}"

        # 确保 nautilus 日志目录存在
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        log_directory = os.path.join(backend_dir, "logs", "worker")
        os.makedirs(log_directory, exist_ok=True)
        log_file_name = f"worker_{worker_id}.log"

        node_config, (data_factory, exec_factory, venue) = build_trading_node_config(
            exchange=exchange,
            account_type=account_type,
            trading_mode=trading_mode,
            trader_id=trader_id,
            log_directory=log_directory,
            log_file_name=log_file_name,
        )

        # 为每个 TradingNode 创建独立事件循环（不共享 uvicorn 主循环）
        # 这样 node.run() 会调用 run_until_complete() 真正阻塞，
        # node.stop() 也能通过 run_coroutine_threadsafe() 真正停止引擎
        node_loop = asyncio.new_event_loop()

        # 创建 TradingNode（传入独立循环，避免使用 uvicorn 主循环）
        node = TradingNode(config=node_config, loop=node_loop)

        # 注册数据客户端和执行客户端工厂
        node.add_data_client_factory(venue, data_factory)
        node.add_exec_client_factory(venue, exec_factory)

        # 将 node.build() 移到 daemon 线程中执行（需要在独立循环上下文中构建）

        # 启动日志刷新线程（解决 nautilus BufWriter 8KB 缓冲导致日志延迟写入的问题）
        _flush_stop = threading.Event()

        def _flush_loop():
            while not _flush_stop.is_set():
                _flush_stop.wait(timeout=2.0)
                if not _flush_stop.is_set():
                    try:
                        flush_logger()
                    except Exception:
                        pass

        flush_thread = threading.Thread(
            target=_flush_loop,
            name=f"nautilus-flush-{worker_id}",
            daemon=True,
        )
        flush_thread.start()
        strategy_registry.set_flush_stop(worker_id, _flush_stop)

        # 加载策略类和配置
        strategy_class = None
        strategy_config = None
        try:
            strategy_class, strategy_config = load_strategy_from_path(worker, db)
            logger.info(
                f"[NautilusTradingSystem] 策略已加载: worker_id={worker_id}, "
                f"strategy_class={strategy_class.__name__ if strategy_class else None}"
            )
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 策略加载失败: worker_id={worker_id}, "
                f"error={e}\n{traceback.format_exc()}"
            )

        # 创建 daemon 线程运行 TradingNode（不阻塞事件循环，Ctrl+C 可强制退出）
        run_thread = threading.Thread(
            target=self._run_node_sync,
            args=(worker_id, node, node_loop, strategy_class, strategy_config),
            name=f"nautilus-worker-{worker_id}",
            daemon=True,
        )
        run_thread.start()

        # 更新注册表
        strategy_registry.set_trading_node(worker_id, node)
        strategy_registry.set_run_thread(worker_id, run_thread)
        strategy_registry.update_status(worker_id, "running")

        runtime.set_pid(os.getpid())

        if runtime.started_at is None:
            runtime.started_at = datetime.now(timezone.utc).isoformat()

        # 更新数据库状态
        if db is not None:
            crud.update_worker_status(db, worker_id, "running", pid=os.getpid())
            db.commit()

        await worker_state_manager.transition(worker_id, "running")

        logger.info(
            f"[NautilusTradingSystem] 策略已启动: worker_id={worker_id}, "
            f"trader_id={trader_id}"
        )
        return True

    def _run_node_sync(self, worker_id: int, node, node_loop, strategy_class=None, strategy_config=None) -> None:
        """
        在 daemon 线程中，使用独立事件循环运行 TradingNode

        关键设计：
        - 每个 TradingNode 拥有独立的 asyncio 事件循环，不与 uvicorn 主循环共享
        - node_loop 未运行 → node.run() 调用 run_until_complete() → 真正阻塞
        - node.stop() 可以通过 run_coroutine_threadsafe() 从其他线程真正停止引擎
        - daemon 线程生命周期与 TradingNode 生命周期完全一致
        """
        from .state import strategy_registry

        asyncio.set_event_loop(node_loop)
        try:
            logger.info(
                f"[NautilusTradingSystem] TradingNode 构建中: worker_id={worker_id}"
            )

            # 注册策略到 trader（必须在 node.build() 之前）
            if strategy_class is not None:
                try:
                    strategy_instance = strategy_class(config=strategy_config)
                    node.trader.add_strategy(strategy_instance)
                    logger.info(
                        f"[NautilusTradingSystem] 策略已注册到 Trader: "
                        f"worker_id={worker_id}, strategy={strategy_class.__name__}"
                    )
                except Exception as e:
                    logger.error(
                        f"[NautilusTradingSystem] 注册策略失败: "
                        f"worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
                    )

            node.build()
            logger.info(
                f"[NautilusTradingSystem] TradingNode 开始运行(Thread): worker_id={worker_id}"
            )

            # 注册 LiveTradeRecorder 事件处理器，订阅 nautilus 事件并持久化到 DB
            try:
                from .event_handler import NautilusEventHandler
                import threading

                _event_buffer: list = []
                _event_buffer_lock = threading.Lock()
                _FLUSH_THRESHOLD = 20

                def _flush_event_buffer() -> None:
                    """将缓冲区中的事件批量写入DB"""
                    nonlocal _event_buffer
                    with _event_buffer_lock:
                        if not _event_buffer:
                            return
                        batch = _event_buffer[:]
                        _event_buffer.clear()

                    try:
                        from utils.db_session import get_db_session as _get_db_session
                        from worker.models import WorkerLog
                        with _get_db_session() as _db:
                            for ev_type, ev_data in batch:
                                log_entry = WorkerLog(
                                    worker_id=worker_id,
                                    level="INFO",
                                    message=json.dumps({
                                        "event_type": ev_type,
                                        **ev_data,
                                    }),
                                    source="LiveTradeRecorder",
                                )
                                _db.add(log_entry)
                            _db.commit()
                    except Exception as flush_err:
                        logger.warning(
                            f"[LiveTradeRecorder] 批量写入异常: "
                            f"worker_id={worker_id}, error={flush_err}"
                        )

                def _live_trade_event_callback(event_type: str, event_data: dict) -> None:
                    """回调：将 nautilus 事件缓冲后批量写入数据库"""
                    try:
                        with _event_buffer_lock:
                            _event_buffer.append((event_type, event_data))
                            should_flush = len(_event_buffer) >= _FLUSH_THRESHOLD
                        if should_flush:
                            _flush_event_buffer()
                    except Exception as cb_err:
                        logger.warning(
                            f"[LiveTradeRecorder] 事件回调异常: "
                            f"worker_id={worker_id}, error={cb_err}"
                        )

                recorder = NautilusEventHandler(
                    trader=node.trader,
                    event_callback=_live_trade_event_callback,
                    node=node,  # 传入 node 以便访问 msgbus
                )
                recorder.subscribe_events()
                logger.info(
                    f"[NautilusTradingSystem] LiveTradeRecorder 已注册: "
                    f"worker_id={worker_id}"
                )
            except Exception as e:
                logger.warning(
                    f"[NautilusTradingSystem] LiveTradeRecorder 注册失败 "
                    f"(非致命): worker_id={worker_id}, error={e}"
                )

            node.run()
        except RuntimeError as e:
            error_msg = str(e)
            if "Event loop stopped before Future completed" in error_msg:
                logger.info(
                    f"[NautilusTradingSystem] TradingNode 正常停止: "
                    f"worker_id={worker_id}"
                )
            else:
                logger.error(
                    f"[NautilusTradingSystem] TradingNode RuntimeError: "
                    f"worker_id={worker_id}, error={error_msg}\n{traceback.format_exc()}"
                )
                strategy_registry.update_status(
                    worker_id, "error", error_message=error_msg
                )
                strategy_registry.set_run_thread(worker_id, None)
                strategy_registry.set_trading_node(worker_id, None)
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"[NautilusTradingSystem] TradingNode 异常: "
                f"worker_id={worker_id}, error={error_msg}\n{traceback.format_exc()}"
            )
            strategy_registry.update_status(
                worker_id, "error", error_message=error_msg
            )
            strategy_registry.set_run_thread(worker_id, None)
            strategy_registry.set_trading_node(worker_id, None)
        finally:
            logger.info(
                f"[NautilusTradingSystem] TradingNode 已结束: worker_id={worker_id}"
            )
            # 立即刷新日志缓冲区
            try:
                flush_logger()
            except Exception:
                pass
            # 线程退出后同步状态为 stopped
            runtime = strategy_registry.get(worker_id)
            if runtime is not None and runtime.status == "running":
                strategy_registry.update_status(worker_id, "stopped")
                logger.info(
                    f"[NautilusTradingSystem] TradingNode 线程已退出, "
                    f"状态已同步为 stopped: worker_id={worker_id}"
                )
            # 关闭独立事件循环
            try:
                if not node_loop.is_closed():
                    node_loop.close()
            except Exception:
                pass

    async def stop_strategy(self, worker_id: int) -> bool:
        """
        停止策略

        支持两种场景：
        1. 正常运行中 stop → 调用 node.stop() + 等待线程退出 + 清理资源
        2. 状态不一致时 stop（status=running 但 is_running=False）→ 强制清理引用，确保状态过渡到 stopped

        Args:
            worker_id: Worker ID

        Returns:
            是否停止成功（清理完成后始终返回 True）
        """
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            raise WorkerNotFoundException(worker_id)

        # 如果 worker 已经处于 stopped 状态，直接返回 True
        if runtime.status == "stopped":
            logger.info(
                f"[NautilusTradingSystem] Worker {worker_id} 已经处于 stopped 状态"
            )
            return True

        # 检测状态不一致：status=running 但 is_running=False（线程意外退出）
        if not runtime.is_running and runtime.status == "running":
            logger.warning(
                f"[NautilusTradingSystem] Worker {worker_id} 状态不一致 "
                f"(status=running, is_running=False), 进入强制清理模式"
            )
            await worker_state_manager.transition(worker_id, "stopping")
            strategy_registry.set_run_thread(worker_id, None)
            strategy_registry.set_trading_node(worker_id, None)
            _flush_stop = strategy_registry.get_flush_stop(worker_id)
            if _flush_stop is not None:
                _flush_stop.set()
                strategy_registry.set_flush_stop(worker_id, None)
            runtime.stopped_at = datetime.now(timezone.utc).isoformat()
            strategy_registry.update_status(worker_id, "stopped")
            with get_db_session() as db:
                crud.update_worker_status(db, worker_id, "stopped")
                db.commit()
            await worker_state_manager.transition(worker_id, "stopped")
            logger.info(
                f"[NautilusTradingSystem] 强制清理完成: worker_id={worker_id}"
            )
            return True

        if not runtime.is_running:
            logger.warning(
                f"[NautilusTradingSystem] Worker {worker_id} 不在运行中 (status={runtime.status})"
            )
            return False

        await worker_state_manager.transition(worker_id, "stopping")

        run_thread = runtime._run_thread
        node = runtime.trading_node

        # 使用独立事件循环设计后，node.run() 通过 run_until_complete 阻塞
        # node.stop() 也会检查 is_running()，因为在 run_until_complete 中
        # 循环正在运行，node.stop() 只创建 task 不会等待。
        # 
        # 正确做法：通过 run_coroutine_threadsafe 在独立循环上调度 stop_async()，
        # stop_async() 会取消所有 engine tasks → run_until_complete 返回
        # → node.run() 返回 → daemon 线程退出 → 我们 join 线程即可完成停止
        if node is not None and hasattr(node, 'kernel') and node.kernel is not None:
            try:
                logger.info(
                    f"[NautilusTradingSystem] 正在停止 TradingNode: worker_id={worker_id}"
                )
                node_loop = node.kernel.loop
                if node_loop is not None and not node_loop.is_closed():
                    future = asyncio.run_coroutine_threadsafe(
                        node.stop_async(), node_loop
                    )
                    try:
                        future.result(timeout=10.0)
                        logger.info(
                            f"[NautilusTradingSystem] node.stop_async() 完成: worker_id={worker_id}"
                        )
                    except TimeoutError:
                        logger.warning(
                            f"[NautilusTradingSystem] node.stop_async() 超时(10s): worker_id={worker_id}"
                        )
                else:
                    logger.warning(
                        f"[NautilusTradingSystem] 事件循环已关闭，跳过 stop_async: worker_id={worker_id}"
                    )
            except Exception as e:
                logger.error(
                    f"[NautilusTradingSystem] 停止 TradingNode 异常: "
                    f"worker_id={worker_id}, error={e}"
                )

        # 等待 daemon 线程退出（stop_async 完成后 run_until_complete 应返回，线程自然退出）
        if run_thread is not None and run_thread.is_alive():
            run_thread.join(timeout=10.0)
            if run_thread.is_alive():
                logger.warning(
                    f"[NautilusTradingSystem] 运行线程未在10s内退出: worker_id={worker_id}"
                )

        strategy_registry.set_run_thread(worker_id, None)
        strategy_registry.set_trading_node(worker_id, None)

        # 停止日志刷新线程
        _flush_stop = strategy_registry.get_flush_stop(worker_id)
        if _flush_stop is not None:
            _flush_stop.set()
            strategy_registry.set_flush_stop(worker_id, None)

        runtime.stopped_at = datetime.now(timezone.utc).isoformat()
        strategy_registry.update_status(worker_id, "stopped")

        try:
            with get_db_session() as db:
                crud.update_worker_status(db, worker_id, "stopped")
                db.commit()
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 更新数据库状态失败: "
                f"worker_id={worker_id}, error={e}"
            )

        await worker_state_manager.transition(worker_id, "stopped")

        logger.info(f"[NautilusTradingSystem] 策略已停止: worker_id={worker_id}")
        return True

    async def delete_strategy(self, worker_id: int) -> bool:
        """
        删除策略

        先停止运行中的策略，再从注册表和数据库中删除。

        Args:
            worker_id: Worker ID

        Returns:
            是否删除成功
        """
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            raise WorkerNotFoundException(worker_id)

        if runtime.is_running:
            await self.stop_strategy(worker_id)

        strategy_registry.unregister(worker_id)
        await worker_state_manager.remove_worker(worker_id)

        try:
            with get_db_session() as db:
                crud.delete_worker(db, worker_id)
                db.commit()
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 删除策略失败: "
                f"worker_id={worker_id}, error={e}"
            )
            return False

        logger.info(f"[NautilusTradingSystem] 策略已删除: worker_id={worker_id}")
        return True

    async def run_backtest(
        self,
        worker_id: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行回测

        在 run_in_executor 中运行同步阻塞的 BacktestEngine。

        Args:
            worker_id: Worker ID
            start_time: 回测开始时间（ISO 8601 格式）
            end_time: 回测结束时间（ISO 8601 格式）

        Returns:
            回测结果字典
        """
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            raise ValueError(f"Worker {worker_id} 不存在")

        # 回测在 executor 中执行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            self._do_run_backtest_sync,
            worker_id,
            start_time,
            end_time,
        )

        logger.info(
            f"[NautilusTradingSystem] 回测完成: worker_id={worker_id}"
        )
        return result

    def _do_run_backtest_sync(
        self,
        worker_id: int,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> Dict[str, Any]:
        """同步回测执行（在 executor 线程中运行）"""
        try:
            with get_db_session() as db:
                worker = crud.get_worker(db, worker_id)
                if worker is None:
                    return {"error": f"Worker {worker_id} 不存在"}

                logger.warning(
                    f"[NautilusTradingSystem] 回测功能尚未集成 NautilusTrader BacktestEngine, "
                    f"worker_id={worker_id}"
                )

                return {
                    "worker_id": worker_id,
                    "status": "not_implemented",
                    "message": "回测功能将在后续版本中集成 NautilusTrader BacktestEngine",
                }
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 回测执行失败: "
                f"worker_id={worker_id}, error={e}"
            )
            return {"error": str(e)}

    def get_strategy_state(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """
        获取策略运行时状态

        Args:
            worker_id: Worker ID

        Returns:
            策略状态字典，不存在返回 None
        """
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            return None
        return runtime.to_dict()

    def list_strategies(self) -> List[Dict[str, Any]]:
        """
        列出所有策略摘要

        Returns:
            策略状态字典列表
        """
        from .state import strategy_registry

        return [rt.to_dict() for rt in strategy_registry.list_all()]

    def get_system_state(self) -> Dict[str, Any]:
        """
        获取系统整体状态

        Returns:
            系统状态字典
        """
        from .state import strategy_registry

        strategies = strategy_registry.list_all()
        running_count = sum(1 for s in strategies if s.is_running)
        error_count = sum(1 for s in strategies if s.status == "error")

        return {
            "total_strategies": len(strategies),
            "running_strategies": running_count,
            "error_strategies": error_count,
            "nautilus_available": NAUTILUS_AVAILABLE,
        }

    def get_summary(self) -> Dict[str, Any]:
        """
        获取系统摘要（供 lifespan 层使用）

        Returns:
            包含 total_workers 和 status_breakdown 的摘要字典
        """
        state = self.get_system_state()

        from .state import strategy_registry
        strategies = strategy_registry.list_all()

        status_counts: Dict[str, int] = {}
        for s in strategies:
            status = s.status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_workers": state["total_strategies"],
            "status_breakdown": status_counts,
        }

    @staticmethod
    def _dump_active_threads() -> str:
        """诊断工具：输出当前所有活跃线程信息"""
        lines = []
        lines.append(f"=== SHUTDOWN DIAGNOSTIC: Active Threads ({threading.active_count()}) ===")
        for t in threading.enumerate():
            lines.append(
                f"  Thread: name={t.name}, daemon={t.daemon}, "
                f"alive={t.is_alive()}, ident={t.ident}"
            )
        lines.append("=== END THREAD DUMP ===")
        return "\n".join(lines)

    def shutdown(self) -> None:
        """
        关闭系统，释放资源

        独立事件循环模式：
        - 每个 TradingNode 有独立事件循环，daemon 线程因 run_until_complete 而阻塞
        - 优先使用 NautilusTrader 内置的 node.stop() 优雅停止
        - 如果优雅停止超时，回退到 loop.stop() 强制停止
        - 状态记录 + 线程诊断 + 线程池关闭
        """
        import traceback

        start_time = time.monotonic()
        logger.info(
            f"[NautilusTradingSystem] ========== shutdown 开始 ==========\n"
            f"{self._dump_active_threads()}"
        )

        from .state import strategy_registry

        strategies = strategy_registry.list_all()
        logger.info(
            f"[NautilusTradingSystem] shutdown: 共 {len(strategies)} 个策略, "
            f"其中运行中 {sum(1 for s in strategies if s.is_running)} 个"
        )

        # 步骤 1: 优雅停止所有 TradingNode（优先使用 node.stop()）
        for runtime in strategies:
            worker_id = runtime.worker_id
            node = runtime.trading_node

            if not runtime.is_running:
                logger.info(
                    f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                    f"status={runtime.status}, 跳过"
                )
                if runtime.status == "running":
                    strategy_registry.update_status(worker_id, "stopping")
                continue

            run_thread = runtime._run_thread
            thread_alive = run_thread is not None and run_thread.is_alive()
            logger.info(
                f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                f"status={runtime.status}, run_thread_alive={thread_alive}"
            )

            # 尝试优雅停止 TradingNode
            if node is not None and hasattr(node, 'kernel') and node.kernel is not None:
                node_loop = node.kernel.loop
                if node_loop is not None and not node_loop.is_closed():
                    try:
                        # 方案1: 使用 NautilusTrader 内置的优雅停止方法 ✅
                        # node.stop() 会调用 stop_async() 优雅清理资源
                        # 避免直接调用 loop.stop() 导致 RuntimeError
                        logger.info(
                            f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                            f"尝试优雅停止 (node.stop())..."
                        )

                        # 在独立线程中调用 node.stop()，避免阻塞主线程
                        def _graceful_stop():
                            try:
                                node.stop()
                                logger.info(
                                    f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                                    f"✓ node.stop() 成功"
                                )
                            except Exception as stop_err:
                                error_msg = str(stop_err)
                                if "Event loop stopped before Future completed" in error_msg:
                                    # 这是正常的停止行为，不是错误
                                    logger.info(
                                        f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                                        f"事件循环已停止 (正常行为)"
                                    )
                                else:
                                    logger.warning(
                                        f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                                        f"node.stop() 异常: {error_msg}"
                                    )

                        stop_thread = threading.Thread(
                            target=_graceful_stop,
                            name=f"nautilus-stop-{worker_id}",
                            daemon=True,
                        )
                        stop_thread.start()

                        # 给优雅停止一点时间（最多0.5秒）
                        stop_thread.join(timeout=0.5)

                        if stop_thread.is_alive():
                            # 如果优雅停止超时，回退到强制停止 loop
                            logger.warning(
                                f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                                f"优雅停止超时 (>0.5s)，回退到 loop.stop()"
                            )
                            try:
                                node_loop.call_soon_threadsafe(node_loop.stop)
                            except Exception as force_err:
                                logger.warning(
                                    f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                                    f"loop.stop 也失败: {force_err}"
                                )

                    except Exception as e:
                        logger.warning(
                            f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                            f"优雅停止失败，尝试强制停止: {e}"
                        )
                        # 回退：直接停止事件循环
                        try:
                            node_loop.call_soon_threadsafe(node_loop.stop)
                        except Exception as force_err:
                            logger.warning(
                                f"[NautilusTradingSystem] shutdown: worker_id={worker_id} "
                                f"强制停止也失败: {force_err}"
                            )

            strategy_registry.update_status(worker_id, "stopping")

        logger.info(
            f"[NautilusTradingSystem] shutdown: 步骤1完成(状态更新), "
            f"耗时 {time.monotonic() - start_time:.3f}s"
        )

        # 步骤 2: 等待所有 daemon 线程退出（最多1秒）
        logger.info("[NautilusTradingSystem] shutdown: 等待 Worker 线程退出...")
        t_start = time.monotonic()

        active_threads = [
            runtime._run_thread
            for runtime in strategies
            if runtime._run_thread is not None and runtime._run_thread.is_alive()
        ]

        if active_threads:
            logger.info(f"[NautilusTradingSystem] shutdown: 还有 {len(active_threads)} 个活跃线程")
            # 给 daemon 线程时间退出（daemon 线程会在主线程退出时自动终止）
            time.sleep(min(1.0, max(0.3, len(active_threads) * 0.1)))

        logger.info(
            f"[NautilusTradingSystem] shutdown: 线程等待完成, "
            f"耗时 {time.monotonic() - t_start:.3f}s"
        )

        # 步骤 3: 关闭线程池
        logger.info("[NautilusTradingSystem] shutdown: 开始关闭 ThreadPoolExecutor...")
        t_start = time.monotonic()
        self._executor.shutdown(wait=False)
        logger.info(
            f"[NautilusTradingSystem] shutdown: ThreadPoolExecutor 已关闭, "
            f"耗时 {time.monotonic() - t_start:.3f}s"
        )

        elapsed = time.monotonic() - start_time
        logger.info(
            f"[NautilusTradingSystem] shutdown: 总耗时 {elapsed:.3f}s\n"
            f"{self._dump_active_threads()}\n"
            f"[NautilusTradingSystem] ========== shutdown 完成 =========="
        )


# =============================================================================
# 模块级单例：worker_system 供 lifespan 和其他模块直接导入使用
# 同时注册到 state.py 的 nautilus_system 单例枢纽
# =============================================================================

worker_system = NautilusTradingSystem()


def _register_to_state() -> None:
    """将实例注册到 state.py 的全局单例"""
    import worker.state as _state

    if _state.nautilus_system is None:
        _state.nautilus_system = worker_system
        logger.info("[NautilusTradingSystem] 已注册到 state.py 单例枢纽")


_register_to_state()


# =========================================================================
# 策略加载函数
# =========================================================================

def load_strategy_from_path(worker, db=None):
    """
    从 Worker ORM 对象加载策略类和配置。

    支持两种加载方式：
    1. 文件加载：策略文件存储在磁盘上（file_path 或 file_name）
    2. 代码加载：策略代码存储在数据库中（code 字段），写入临时文件后加载

    支持两种策略类型：
    - default：原生 NautilusTrader Strategy，使用 load_advanced_strategy() 加载
    - legacy：基于 StrategyBase 的旧策略，使用 adapt_legacy_strategy() 包装

    Args:
        worker: Worker ORM 对象（需通过 session 确保 strategy 关系已加载）
        db: 数据库会话（可选，用于懒加载 strategy 关系）

    Returns:
        (strategy_class, strategy_config_dict) 元组

    Raises:
        ValueError: 如果策略配置无效或找不到策略
        Exception: 加载失败时的其他异常
    """
    from strategy.models import Strategy
    from backtest.adapters.strategy_adapter import (
        load_advanced_strategy,
        adapt_legacy_strategy,
    )

    # 1. 获取 Strategy ORM 对象
    strategy = getattr(worker, "strategy", None)
    if strategy is None and worker.strategy_id is not None:
        if db is None:
            from collector.db.database import SessionLocal as _SessionLocal
            db = _SessionLocal()
            own_db = True
        else:
            own_db = False
        try:
            strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()
        finally:
            if own_db:
                db.close()

    if strategy is None:
        raise ValueError(
            f"Worker {worker.id} 没有关联的策略 "
            f"(strategy_id={worker.strategy_id})"
        )

    # 2. 构建策略配置：worker.config (JSON) 合并 strategy.parameters (JSON)
    worker_config = {}
    if worker.config:
        try:
            worker_config = json.loads(worker.config) if isinstance(worker.config, str) else worker.config
        except (json.JSONDecodeError, TypeError):
            worker_config = {}

    strategy_params = {}
    if strategy.parameters:
        try:
            strategy_params = json.loads(strategy.parameters) if isinstance(strategy.parameters, str) else strategy.parameters
        except (json.JSONDecodeError, TypeError):
            strategy_params = {}

    # 合并配置：strategy.parameters 作为基础，worker.config 覆盖
    merged_config = {**strategy_params, **worker_config}

    # 3. 确定策略类型
    strategy_type = getattr(strategy, "strategy_type", "default") or "default"

    # 4. 获取策略代码/文件
    strategy_file_path = getattr(strategy, "file_path", None)
    strategy_file_name = getattr(strategy, "file_name", None)
    strategy_code = getattr(strategy, "code", None)

    temp_file = None

    try:
        if strategy_type == "legacy":
            # ----- Legacy 策略加载 -----
            # Legacy 策略继承自 StrategyBase，需要先导入再包装
            legacy_class = None

            if strategy_file_path and os.path.isfile(strategy_file_path):
                # 从文件加载 legacy 策略
                legacy_class = _load_class_from_file(
                    strategy_file_path, strategy_file_name
                )
            elif strategy_code:
                # 从数据库代码加载 legacy 策略（写入临时文件）
                temp_file = _write_code_to_temp_file(
                    strategy_code, strategy_file_name
                )
                legacy_class = _load_class_from_file(
                    temp_file, strategy_file_name
                )
            else:
                raise ValueError(
                    f"Legacy 策略 {strategy.name} 既没有文件也没有代码"
                )

            # 使用 adapt_legacy_strategy 包装为 Nautilus Strategy
            strategy_class = adapt_legacy_strategy(legacy_class)
            logger.info(
                f"[策略加载] Legacy 策略已包装: {strategy.name} -> "
                f"{strategy_class.__name__}"
            )
        else:
            # ----- Default (原生 Nautilus) 策略加载 -----
            if strategy_file_path and os.path.isfile(strategy_file_path):
                # 从文件加载
                strategy_class = load_advanced_strategy(strategy_file_path)
            elif strategy_code:
                # 从数据库代码加载（写入临时文件）
                temp_file = _write_code_to_temp_file(
                    strategy_code, strategy_file_name
                )
                strategy_class = load_advanced_strategy(temp_file)
            else:
                raise ValueError(
                    f"策略 {strategy.name} 既没有文件也没有代码"
                )

            logger.info(
                f"[策略加载] 原生策略已加载: {strategy.name} -> "
                f"{strategy_class.__name__}"
            )

        return strategy_class, merged_config

    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError:
                pass


def _load_class_from_file(file_path, strategy_name=None):
    """
    从 Python 文件加载策略类（支持 legacy StrategyBase）。

    Args:
        file_path: Python 文件路径
        strategy_name: 策略类名称（可选）

    Returns:
        策略类

    Raises:
        ImportError: 导入失败
        ValueError: 找不到策略类
    """
    import importlib
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"策略文件不存在: {file_path}")

    # 添加策略目录到 sys.path
    strategy_dir = str(path.parent)
    if strategy_dir not in sys.path:
        sys.path.insert(0, strategy_dir)

    module_name = path.stem
    try:
        # 清除模块缓存（避免重复导入）
        if module_name in sys.modules:
            del sys.modules[module_name]

        module = importlib.import_module(module_name)

        if strategy_name and hasattr(module, strategy_name):
            return getattr(module, strategy_name)

        # 自动查找：优先找 StrategyBase 子类，其次找任何类
        try:
            from strategy.core import StrategyBase
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, StrategyBase)
                    and obj is not StrategyBase
                ):
                    return obj
        except ImportError:
            pass

        # 回退：查找任何非私有类
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and not name.startswith("_"):
                return obj

        raise ValueError(
            f"在模块 {module_name} 中找不到策略类"
        )
    except Exception as e:
        raise ImportError(
            f"从文件加载策略失败: {file_path}, error={e}"
        ) from e


def _write_code_to_temp_file(code, file_name=None):
    """
    将数据库中的策略代码写入临时文件。

    Args:
        code: 策略 Python 代码
        file_name: 原始文件名（用于保留 .py 后缀）

    Returns:
        临时文件的路径
    """
    fd, temp_path = tempfile.mkstemp(suffix=".py", prefix="strategy_")

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
    except Exception:
        os.close(fd)
        raise

    logger.info(f"[策略加载] 代码已写入临时文件: {temp_path}")
    return temp_path