# -*- coding: utf-8 -*-
"""
Worker System — AxonTradingSystem 策略执行引擎

基于 axon_quant 的策略生命周期管理引擎，替代原 axon_quantTradingSystem。

职责:
    - 策略生命周期管理（创建、启动、停止、删除）
    - axon_quant exchange adapter 的构建与运行
    - 回测执行
    - 启动时从数据库恢复策略状态
    - 三层策略管理：全局单例 + 内存注册表 + 数据库持久化
"""

import asyncio
import json
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.db_session import get_db_session
from utils.logger import get_logger, LogType

from . import crud
from .exceptions import (
    WorkerNotFoundException,
    WorkerAlreadyRunningException,
)
from .worker_state import WorkerState, worker_state_manager, WorkerStateManager

logger = get_logger(__name__, LogType.APPLICATION)

# axon_quant 导入（可选）
try:
    from axond.exchange_config import build_exchange_config
    from axond.paper_adapter import PaperExchangeAdapter, build_paper_adapter
    from axond.strategy_loop import StrategyLoop
    AXON_AVAILABLE = True
except ImportError as e:
    AXON_AVAILABLE = False
    logger.warning(f"[AxonTradingSystem] axond 模块不可用: {e}")


def _build_exchange_adapter(exchange: str, trading_mode: str):
    """根据交易模式选择 exchange adapter。

    paper 模式：使用内存 PaperExchangeAdapter（无外部依赖）
    live/testnet：当前回退到 PaperExchangeAdapter（后续可替换为真实 adapter）

    返回的 adapter 必须实现 StrategyLoop 约定的接口：
    connect / disconnect / subscribe / get_ticker / place_order
    """
    if trading_mode == "paper" or not AXON_AVAILABLE:
        return build_paper_adapter(exchange=exchange, trading_mode=trading_mode)
    # live / testnet 占位：暂用 paper adapter，后续替换为真实交易所 adapter
    return build_paper_adapter(exchange=exchange, trading_mode="paper")


class AxonTradingSystem:
    """
    axon_quant 策略执行引擎（单例）

    作为整个 Worker 模块的核心，管理所有策略的完整生命周期。
    使用 axon_quant 的 exchange adapter 替代 交易引擎的 TradingNode。

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
            max_workers = min(cpu_count, 8)
        
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="axon-backtest",
        )
        self._strategy_loops: Dict[int, StrategyLoop] = {}
        logger.info(f"[AxonTradingSystem] ThreadPoolExecutor 初始化: max_workers={max_workers}")

    async def initialize(self) -> None:
        """初始化系统，从数据库恢复策略状态"""
        async with self._lock:
            if self._initialized:
                return
            self._initialized = True

        logger.info("[AxonTradingSystem] 正在初始化...")

        await worker_state_manager.initialize()

        if not AXON_AVAILABLE:
            logger.warning("[AxonTradingSystem] axond 模块不可用，策略管理功能受限")
            return

        await self._load_workers_from_db()

        logger.info("[AxonTradingSystem] 初始化完成")

    def _validate_worker_config(self, worker, db=None) -> None:
        """验证 worker 配置是否合法，不合法抛出 ValueError"""
        if not worker.strategy_id:
            raise ValueError(f"worker {worker.id} 未关联策略 (strategy_id 为空)")

        if worker.config:
            try:
                config = json.loads(worker.config) if isinstance(worker.config, str) else worker.config
                if not isinstance(config, dict):
                    raise ValueError(
                        f"worker.config 类型异常: {type(config).__name__}，期望 dict"
                    )
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"worker.config JSON 解析失败: {e}")

        strategy = getattr(worker, "strategy", None)
        if strategy is None and db is not None:
            from strategy.models import Strategy
            strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()
        if strategy and strategy.parameters:
            try:
                params = json.loads(strategy.parameters) if isinstance(strategy.parameters, str) else strategy.parameters
                if isinstance(params, list):
                    raise ValueError(
                        f"策略 {strategy.id} 的 parameters 是 list 类型，"
                        f"期望 dict。请将参数改为 dict 格式后重启"
                    )
                if not isinstance(params, dict):
                    raise ValueError(
                        f"策略 {strategy.id} 的 parameters 类型异常: {type(params).__name__}"
                    )
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"策略 parameters JSON 解析失败: {e}")

    async def _load_workers_from_db(self) -> None:
        """从数据库加载 worker 配置到内存注册表"""
        from .state import strategy_registry, StrategyRuntime

        with get_db_session() as db:
            workers, total = crud.get_workers(db, skip=0, limit=1000)
            logger.info(f"[AxonTradingSystem] 从数据库加载了 {total} 个策略配置")

            config_errors = []

            for worker in workers:
                runtime = StrategyRuntime(
                    worker_id=worker.id,
                    strategy_id=worker.strategy_id,
                    name=worker.name or f"worker-{worker.id}",
                    status=worker.status or "stopped",
                )
                strategy_registry.register(runtime)

                if worker.status == "running":
                    try:
                        self._validate_worker_config(worker, db)
                    except ValueError as e:
                        error_msg = f"配置验证失败: {e}"
                        logger.error(
                            f"[AxonTradingSystem] 策略配置异常，跳过启动: "
                            f"worker_id={worker.id}, name={worker.name}, error={e}"
                        )
                        strategy_registry.update_status(
                            worker.id, "error", error_message=error_msg
                        )
                        config_errors.append({
                            "worker_id": worker.id,
                            "name": worker.name,
                            "error": str(e),
                        })
                        continue

                    logger.info(
                        f"[AxonTradingSystem] 恢复启动运行中的策略: "
                        f"worker_id={worker.id}, name={worker.name}"
                    )
                    try:
                        await self._do_start_strategy(worker.id, worker)
                    except Exception as e:
                        logger.error(
                            f"[AxonTradingSystem] 恢复启动策略失败: "
                            f"worker_id={worker.id}, error={e}"
                        )
                        strategy_registry.update_status(
                            worker.id, "error", error_message=str(e)
                        )

            if config_errors:
                logger.warning(
                    f"[AxonTradingSystem] {len(config_errors)} 个策略配置异常，"
                    f"已标记为 error 状态，请修复后重启"
                )

    async def create_strategy(self, db, worker_config: Dict[str, Any]) -> int:
        """创建策略

        Args:
            db: 数据库会话
            worker_config: 策略配置字典

        Returns:
            worker_id
        """
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
            f"[AxonTradingSystem] 策略已创建: worker_id={worker.id}, "
            f"name={worker.name}"
        )
        return worker.id

    async def start_strategy(self, worker_id: int) -> bool:
        """启动策略

        Args:
            worker_id: Worker ID

        Returns:
            是否启动成功
        """
        try:
            with get_db_session() as db:
                worker = crud.get_worker(db, worker_id)
                if worker is None:
                    raise WorkerNotFoundException(worker_id)

                logger.info(
                    f"[AxonTradingSystem] ===== start_strategy 被调用 ====="
                    f"\n  worker_id={worker_id} (type={type(worker_id).__name__})"
                    f"\n  数据库 name={worker.name}"
                )

                await worker_state_manager.transition(worker_id, "starting")
                return await self._do_start_strategy(worker_id, worker, db)
        except WorkerNotFoundException as e:
            logger.warning(f"[AxonTradingSystem] {e.message}")
            return False
        except Exception as e:
            logger.error(
                f"[AxonTradingSystem] 启动策略失败: worker_id={worker_id}, "
                f"error={e}\n{traceback.format_exc()}"
            )
            await worker_state_manager.transition(
                worker_id, "error", error_message=str(e)
            )
            return False

    async def _do_start_strategy(self, worker_id: int, worker, db=None) -> bool:
        """实际执行策略启动操作

        使用 axon_quant 的 exchange adapter 替代 交易引擎的 TradingNode。

        Args:
            worker_id: Worker ID
            worker: Worker ORM 对象
            db: 数据库会话（可选）

        Returns:
            是否启动成功
        """
        from .state import strategy_registry

        logger.info(
            f"[AxonTradingSystem] ===== _do_start_strategy 开始 ====="
            f"\n  入参 worker_id={worker_id} (type={type(worker_id).__name__})"
            f"\n  入参 worker.id={worker.id} (type={type(worker.id).__name__})"
            f"\n  入参 worker.name={worker.name}"
        )

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            logger.warning(
                f"[AxonTradingSystem] Worker {worker_id} 不在注册表中"
            )
            return False

        if runtime.is_running:
            raise WorkerAlreadyRunningException(worker_id)

        # 获取交易所配置
        exchange = getattr(worker, 'exchange', 'binance') or 'binance'
        if hasattr(exchange, 'value'):
            exchange = exchange.value

        trading_mode = getattr(worker, 'trading_mode', 'testnet') or 'testnet'
        if hasattr(trading_mode, 'value'):
            trading_mode = trading_mode.value

        # 创建日志目录
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        log_directory = os.path.join(backend_dir, "logs", "worker")
        os.makedirs(log_directory, exist_ok=True)

        # 构建交易所配置
        try:
            exchange_config = build_exchange_config(exchange, trading_mode)
        except Exception as e:
            logger.error(
                f"[AxonTradingSystem] 构建交易所配置失败: worker_id={worker_id}, "
                f"error={e}"
            )
            raise

        # 加载策略
        strategy_class = None
        strategy_config = None
        try:
            from backtest.strategy_loader_service import StrategyLoaderService
            from strategy.models import Strategy
            from axond.types import InstrumentId

            # 关联的策略对象
            strategy = getattr(worker, "strategy", None)
            if strategy is None and db is not None:
                strategy = (
                    db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()
                )

            if strategy is None:
                raise ValueError(f"无法找到 worker {worker_id} 关联的策略")

            # 解析交易配置，获取品种和时间周期
            trading_config = worker.get_trading_config_dict() if hasattr(worker, "get_trading_config_dict") else {}
            symbols = worker.get_symbols() if hasattr(worker, "get_symbols") else []
            timeframe = trading_config.get("timeframe", "1h")

            if not symbols:
                raise ValueError(f"worker {worker_id} 未配置交易品种")

            # 解析策略参数
            params = {}
            if strategy.parameters:
                try:
                    raw_params = (
                        json.loads(strategy.parameters)
                        if isinstance(strategy.parameters, str)
                        else strategy.parameters
                    )
                    if isinstance(raw_params, dict):
                        params = raw_params
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(
                        f"[AxonTradingSystem] 策略参数 JSON 解析失败: {e}"
                    )

            # 通过 axond 体系加载策略
            instruments = {
                symbol: InstrumentId(symbol, "BINANCE") for symbol in symbols
            }
            bar_types = {symbol: timeframe for symbol in symbols}

            strategy_instance = StrategyLoaderService.load_event_strategy_multi(
                strategy_name=strategy.strategy_name or strategy.name,
                strategy_params=params,
                bar_types=bar_types,
                instruments=instruments,
            )

            if strategy_instance is not None:
                strategy_class = type(strategy_instance)
                logger.info(
                    f"[AxonTradingSystem] 策略已加载: worker_id={worker_id}, "
                    f"strategy_class={strategy_class.__name__}"
                )
        except Exception as e:
            logger.error(
                f"[AxonTradingSystem] 策略加载失败: worker_id={worker_id}, "
                f"error={e}\n{traceback.format_exc()}"
            )

        # 创建策略实例
        if strategy_instance is None:
            # 加载失败时使用占位空策略，避免阻断启动流程
            from axond.axon_strategy import AxonStrategy

            class _PlaceholderStrategy(AxonStrategy):
                """占位策略：策略加载失败时使用，不会触发任何交易"""

                def on_bar(self, bar) -> None:  # type: ignore[override]
                    pass

            placeholder_cfg = type("PlaceholderConfig", (), {})()
            placeholder_cfg.instrument_ids = []
            placeholder_cfg.bar_types = []
            strategy_instance = _PlaceholderStrategy(placeholder_cfg)
            strategy_class = _PlaceholderStrategy
            logger.warning(
                f"[AxonTradingSystem] 使用占位策略，worker_id={worker_id}"
            )

        # 获取交易对符号
        symbol = getattr(worker, 'symbol', 'BTCUSDT') or 'BTCUSDT'

        # 构建 exchange adapter（按 trading_mode 选择真实/paper 实现）
        try:
            adapter = _build_exchange_adapter(exchange, trading_mode)
            logger.info(
                f"[AxonTradingSystem] Exchange adapter 已构建: "
                f"worker_id={worker_id}, exchange={exchange}, "
                f"trading_mode={trading_mode}, adapter_type={type(adapter).__name__}"
            )
        except Exception as e:
            logger.error(
                f"[AxonTradingSystem] 构建 exchange adapter 失败: "
                f"worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            raise

        # 创建策略循环
        strategy_loop = StrategyLoop(
            adapter=adapter,
            strategy=strategy_instance,
            symbol=symbol,
        )

        # 保存策略循环引用
        self._strategy_loops[worker_id] = strategy_loop

        # 启动策略循环（在独立线程中）
        try:
            strategy_loop.start()
        except Exception as e:
            logger.error(
                f"[AxonTradingSystem] 启动策略循环失败: worker_id={worker_id}, "
                f"error={e}\n{traceback.format_exc()}"
            )
            raise

        # 更新注册表
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
            f"[AxonTradingSystem] 策略已启动: worker_id={worker_id}"
        )
        return True

    async def stop_strategy(self, worker_id: int) -> bool:
        """停止策略

        Args:
            worker_id: Worker ID

        Returns:
            是否停止成功
        """
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            raise WorkerNotFoundException(worker_id)

        if runtime.status == "stopped":
            logger.info(
                f"[AxonTradingSystem] Worker {worker_id} 已经处于 stopped 状态"
            )
            return True

        await worker_state_manager.transition(worker_id, "stopping")

        # 停止策略循环
        strategy_loop = self._strategy_loops.get(worker_id)
        if strategy_loop is not None:
            try:
                strategy_loop.stop()
            except Exception as e:
                logger.error(
                    f"[AxonTradingSystem] 停止策略循环失败: worker_id={worker_id}, "
                    f"error={e}"
                )
            del self._strategy_loops[worker_id]

        runtime.stopped_at = datetime.now(timezone.utc).isoformat()
        strategy_registry.update_status(worker_id, "stopped")

        try:
            with get_db_session() as db:
                crud.update_worker_status(db, worker_id, "stopped")
                db.commit()
        except Exception as e:
            logger.error(
                f"[AxonTradingSystem] 更新数据库状态失败: "
                f"worker_id={worker_id}, error={e}"
            )

        await worker_state_manager.transition(worker_id, "stopped")

        logger.info(f"[AxonTradingSystem] 策略已停止: worker_id={worker_id}")
        return True

    async def delete_strategy(self, worker_id: int) -> bool:
        """删除策略

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
                f"[AxonTradingSystem] 删除策略失败: "
                f"worker_id={worker_id}, error={e}"
            )
            return False

        logger.info(f"[AxonTradingSystem] 策略已删除: worker_id={worker_id}")
        return True

    def get_strategy_state(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """获取策略运行时状态"""
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            return None
        return runtime.to_dict()

    def list_strategies(self) -> List[Dict[str, Any]]:
        """列出所有策略摘要"""
        from .state import strategy_registry

        return [rt.to_dict() for rt in strategy_registry.list_all()]

    def get_system_state(self) -> Dict[str, Any]:
        """获取系统整体状态"""
        from .state import strategy_registry

        strategies = strategy_registry.list_all()
        running_count = sum(1 for s in strategies if s.is_running)
        error_count = sum(1 for s in strategies if s.status == "error")

        return {
            "total_strategies": len(strategies),
            "running_strategies": running_count,
            "error_strategies": error_count,
            "axon_available": AXON_AVAILABLE,
        }

    def get_summary(self) -> Dict[str, Any]:
        """获取系统摘要（用于日志和状态展示）"""
        from .state import strategy_registry

        strategies = strategy_registry.list_all()
        running_count = sum(1 for s in strategies if s.is_running)
        error_count = sum(1 for s in strategies if s.status == "error")

        return {
            "total_workers": len(strategies),
            "running_workers": running_count,
            "error_workers": error_count,
            "status_breakdown": {
                "running": running_count,
                "error": error_count,
                "stopped": len(strategies) - running_count - error_count,
            },
        }

    def shutdown(self) -> None:
        """关闭系统，释放资源"""
        start_time = time.monotonic()
        logger.info("[AxonTradingSystem] ========== shutdown 开始 ==========")

        from .state import strategy_registry

        strategies = strategy_registry.list_all()
        logger.info(
            f"[AxonTradingSystem] shutdown: 共 {len(strategies)} 个策略, "
            f"其中运行中 {sum(1 for s in strategies if s.is_running)} 个"
        )

        # 停止所有策略循环
        for worker_id, strategy_loop in self._strategy_loops.items():
            try:
                strategy_loop.stop()
                logger.info(
                    f"[AxonTradingSystem] shutdown: worker_id={worker_id} 策略循环已停止"
                )
            except Exception as e:
                logger.warning(
                    f"[AxonTradingSystem] shutdown: worker_id={worker_id} "
                    f"停止策略循环失败: {e}"
                )

        self._strategy_loops.clear()

        # 关闭线程池
        logger.info("[AxonTradingSystem] shutdown: 开始关闭 ThreadPoolExecutor...")
        self._executor.shutdown(wait=False)

        elapsed = time.monotonic() - start_time
        logger.info(
            f"[AxonTradingSystem] shutdown: 总耗时 {elapsed:.3f}s\n"
            f"[AxonTradingSystem] ========== shutdown 完成 =========="
        )


# =============================================================================
# 模块级单例：worker_system 供 lifespan 和其他模块直接导入使用
# =============================================================================

worker_system = AxonTradingSystem()


def _register_to_state() -> None:
    """将实例注册到 state.py 的全局单例"""
    import worker.state as _state

    if _state.axon_system is None:
        _state.axon_system = worker_system
        logger.info("[AxonTradingSystem] 已注册到 state.py 单例枢纽")


_register_to_state()
