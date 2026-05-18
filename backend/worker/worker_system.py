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
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from collector.db.database import SessionLocal
from utils.logger import get_logger, LogType

from . import crud
from .config import build_trading_node_config, NAUTILUS_AVAILABLE, NAUTILUS_MISSING_DETAIL
from .worker_state import WorkerState, worker_state_manager, WorkerStateManager

logger = get_logger(__name__, LogType.APPLICATION)

if NAUTILUS_AVAILABLE:
    try:
        from nautilus_trader.live.node import TradingNode
    except ImportError as e:
        TradingNode = None
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

    def __init__(self):
        self._lock = asyncio.Lock()
        self._initialized = False
        self._executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="nautilus-backtest",
        )

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

        db = SessionLocal()
        try:
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
        except Exception as e:
            logger.error(f"[NautilusTradingSystem] 从数据库加载策略失败: {e}")
        finally:
            db.close()

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

        db = SessionLocal()
        try:
            worker = crud.get_worker(db, worker_id)
            if worker is None:
                logger.warning(f"[NautilusTradingSystem] Worker {worker_id} 不存在")
                return False

            await worker_state_manager.transition(worker_id, "starting")
            return await self._do_start_strategy(worker_id, worker, db)
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 启动策略失败: worker_id={worker_id}, "
                f"error={e}\n{traceback.format_exc()}"
            )
            await worker_state_manager.transition(
                worker_id, "error", error_message=str(e)
            )
            return False
        finally:
            db.close()

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
            logger.warning(
                f"[NautilusTradingSystem] Worker {worker_id} 已在运行中"
            )
            return False

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

        node_config, (data_factory, exec_factory, venue) = build_trading_node_config(
            exchange=exchange,
            account_type=account_type,
            trading_mode=trading_mode,
            trader_id=trader_id,
        )

        # 创建 TradingNode
        node = TradingNode(config=node_config)

        # 注册数据客户端和执行客户端工厂
        node.add_data_client_factory(venue, data_factory)
        node.add_exec_client_factory(venue, exec_factory)

        # TODO: 当自定义策略可用时，在此处加载并注册策略
        # strategy_class = load_strategy_from_path(worker.strategy_path)
        # node.trader.add_strategy(strategy_class(config=config))

        # 创建 asyncio 任务运行 TradingNode
        task = asyncio.create_task(
            self._run_node_with_error_handling(worker_id, node),
            name=f"nautilus-worker-{worker_id}",
        )

        # 更新注册表
        strategy_registry.set_trading_node(worker_id, node)
        strategy_registry.set_run_task(worker_id, task)
        strategy_registry.update_status(worker_id, "running")

        if runtime.started_at is None:
            runtime.started_at = datetime.now(timezone.utc).isoformat()

        # 更新数据库状态
        if db is not None:
            crud.update_worker_status(db, worker_id, "running")
            db.commit()

        await worker_state_manager.transition(worker_id, "running")

        logger.info(
            f"[NautilusTradingSystem] 策略已启动: worker_id={worker_id}, "
            f"trader_id={trader_id}"
        )
        return True

    async def _run_node_with_error_handling(self, worker_id: int, node) -> None:
        """
        运行 TradingNode 并处理异常

        策略异常不会导致主进程崩溃，只会更新状态为 error。
        """
        from .state import strategy_registry

        try:
            logger.info(
                f"[NautilusTradingSystem] TradingNode 开始运行: worker_id={worker_id}"
            )
            node.run()
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"[NautilusTradingSystem] TradingNode 异常: "
                f"worker_id={worker_id}, error={error_msg}\n{traceback.format_exc()}"
            )
            strategy_registry.update_status(
                worker_id, "error", error_message=error_msg
            )
            await worker_state_manager.transition(
                worker_id, "error", error_message=error_msg
            )
        finally:
            try:
                node.dispose()
            except Exception as e:
                logger.warning(
                    f"[NautilusTradingSystem] TradingNode dispose 失败: "
                    f"worker_id={worker_id}, error={e}"
                )
            logger.info(
                f"[NautilusTradingSystem] TradingNode 已结束: worker_id={worker_id}"
            )

    async def stop_strategy(self, worker_id: int) -> bool:
        """
        停止策略

        Args:
            worker_id: Worker ID

        Returns:
            是否停止成功
        """
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            logger.warning(
                f"[NautilusTradingSystem] Worker {worker_id} 不在注册表中"
            )
            return False

        if not runtime.is_running:
            logger.warning(
                f"[NautilusTradingSystem] Worker {worker_id} 未在运行中"
            )
            return False

        await worker_state_manager.transition(worker_id, "stopping")

        task = runtime._run_task
        node = runtime.trading_node

        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(
                    f"[NautilusTradingSystem] 停止策略时 task 异常: "
                    f"worker_id={worker_id}, error={e}"
                )

        if node is not None:
            try:
                node.dispose()
            except Exception as e:
                logger.warning(
                    f"[NautilusTradingSystem] dispose 异常: "
                    f"worker_id={worker_id}, error={e}"
                )

        strategy_registry.set_run_task(worker_id, None)
        strategy_registry.set_trading_node(worker_id, None)

        runtime.stopped_at = datetime.now(timezone.utc).isoformat()
        strategy_registry.update_status(worker_id, "stopped")

        db = SessionLocal()
        try:
            crud.update_worker_status(db, worker_id, "stopped")
            db.commit()
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 更新数据库状态失败: "
                f"worker_id={worker_id}, error={e}"
            )
        finally:
            db.close()

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
            return False

        if runtime.is_running:
            await self.stop_strategy(worker_id)

        strategy_registry.unregister(worker_id)
        await worker_state_manager.remove_worker(worker_id)

        db = SessionLocal()
        try:
            crud.delete_worker(db, worker_id)
            db.commit()
        except Exception as e:
            logger.error(
                f"[NautilusTradingSystem] 删除策略失败: "
                f"worker_id={worker_id}, error={e}"
            )
            return False
        finally:
            db.close()

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
        db = SessionLocal()
        try:
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
        finally:
            db.close()

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

    def shutdown(self) -> None:
        """关闭系统，释放资源"""
        self._executor.shutdown(wait=True)
        logger.info("[NautilusTradingSystem] 已关闭")


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