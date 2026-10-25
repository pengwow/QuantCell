"""
StrategyManager — 统一策略执行引擎

基于 axon_quant 的策略生命周期管理引擎，统一管理所有策略的完整生命周期。

职责:
    - 策略生命周期管理（创建、启动、停止、删除、注册）
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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

from . import crud
from .exceptions import (
    WorkerAlreadyRunningException,
    WorkerNotFoundException,
)
from .worker_state import worker_state_manager

logger = get_logger(__name__, LogType.APPLICATION)

# RL paper 循环支持的 K 线周期 → 周期秒数（与 exchange/base.py 的 interval 映射同口径；
# 键同时作为 binance REST 的 interval 参数，周期外直接在装配期拒绝）
_RL_PAPER_INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# RL paper 行情轮询端点：testnet 公共 K 线，不签名、无需凭证
_RL_PAPER_KLINES_URL = "https://testnet.binancefuture.com/fapi/v1/klines"

# axon_quant 导入
try:
    from strategy.loop import StrategyLoop

    AXON_AVAILABLE = True
except ImportError as e:
    AXON_AVAILABLE = False
    logger.warning(f"[StrategyManager] strategy.loop 不可用: {e}")


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


class StrategyManager:
    """
    统一策略执行引擎（单例）

    作为整个系统的核心，管理所有策略的完整生命周期。
    使用 axon_quant 的 exchange adapter 执行策略。

    架构层次:
        1. 全局单例层: 由 state.py 统一持有单例引用
        2. 内存存储层: StrategyRegistry 字典（worker_id → StrategyRuntime）
        3. 数据库持久化层: crud.py 操作 SQLite
    """

    def __init__(self, max_workers: int | None = None):
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
        self._strategy_loops: dict[int, StrategyLoop] = {}
        # RL 策略已装配但尚未被数据泵驱动的内核（worker_id → worker.Kernel）
        self._rl_kernels: dict[int, Any] = {}
        # RL 循环运行态（worker_id → {driver, stop_event, thread}），live/paper 共用：
        # live 额外带 journal_path，paper 无持久化；停机统一走 stop_strategy 的 RL 块
        self._rl_live: dict[int, dict[str, Any]] = {}
        logger.info(f"[StrategyManager] ThreadPoolExecutor 初始化: max_workers={max_workers}")

    async def initialize(self) -> None:
        """初始化系统，从数据库恢复策略状态"""
        async with self._lock:
            if self._initialized:
                return
            self._initialized = True

        logger.info("[StrategyManager] 正在初始化...")

        await worker_state_manager.initialize()

        if not AXON_AVAILABLE:
            logger.warning("[StrategyManager] axond 模块不可用，策略管理功能受限")
            return

        await self._load_workers_from_db()

        logger.info("[StrategyManager] 初始化完成")

    def _validate_worker_config(self, worker, db=None) -> None:
        """验证 worker 配置是否合法，不合法抛出 ValueError"""
        if not worker.strategy_id:
            msg = f"worker {worker.id} 未关联策略 (strategy_id 为空)"
            raise ValueError(msg)

        if worker.config:
            try:
                config = json.loads(worker.config) if isinstance(worker.config, str) else worker.config
                if not isinstance(config, dict):
                    msg = f"worker.config 类型异常: {type(config).__name__}，期望 dict"
                    raise ValueError(msg)
            except (json.JSONDecodeError, TypeError) as e:
                msg = f"worker.config JSON 解析失败: {e}"
                raise ValueError(msg)

        strategy = getattr(worker, "strategy", None)
        if strategy is None and db is not None:
            from strategy.models import Strategy

            strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()
        if strategy and strategy.parameters:
            try:
                params = (
                    json.loads(strategy.parameters) if isinstance(strategy.parameters, str) else strategy.parameters
                )
                if isinstance(params, list):
                    msg = f"策略 {strategy.id} 的 parameters 是 list 类型，期望 dict。请将参数改为 dict 格式后重启"
                    raise ValueError(msg)
                if not isinstance(params, dict):
                    msg = f"策略 {strategy.id} 的 parameters 类型异常: {type(params).__name__}"
                    raise ValueError(msg)
            except (json.JSONDecodeError, TypeError) as e:
                msg = f"策略 parameters JSON 解析失败: {e}"
                raise ValueError(msg)

    async def _load_workers_from_db(self) -> None:
        """从数据库加载 worker 配置到内存注册表"""
        from .state import StrategyRuntime, strategy_registry

        with get_db_session() as db:
            workers, total = crud.get_workers(db, skip=0, limit=1000)
            logger.info(f"[StrategyManager] 从数据库加载了 {total} 个策略配置")

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
                            f"[StrategyManager] 策略配置异常，跳过启动: "
                            f"worker_id={worker.id}, name={worker.name}, error={e}"
                        )
                        strategy_registry.update_status(worker.id, "error", error_message=error_msg)
                        config_errors.append(
                            {
                                "worker_id": worker.id,
                                "name": worker.name,
                                "error": str(e),
                            }
                        )
                        continue

                    logger.info(f"[StrategyManager] 恢复启动运行中的策略: worker_id={worker.id}, name={worker.name}")
                    try:
                        await self._do_start_strategy(worker.id, worker)
                    except Exception as e:
                        logger.error(f"[StrategyManager] 恢复启动策略失败: worker_id={worker.id}, error={e}")
                        strategy_registry.update_status(worker.id, "error", error_message=str(e))

            if config_errors:
                logger.warning(
                    f"[StrategyManager] {len(config_errors)} 个策略配置异常，已标记为 error 状态，请修复后重启"
                )

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
                    f"[StrategyManager] ===== start_strategy 被调用 ====="
                    f"\n  worker_id={worker_id} (type={type(worker_id).__name__})"
                    f"\n  数据库 name={worker.name}"
                )

                await worker_state_manager.transition(worker_id, "starting")
                return await self._do_start_strategy(worker_id, worker, db)
        except WorkerNotFoundException as e:
            logger.warning(f"[StrategyManager] {e.message}")
            return False
        except Exception as e:
            logger.error(f"[StrategyManager] 启动策略失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}")
            await worker_state_manager.transition(worker_id, "error", error_message=str(e))
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
            f"[StrategyManager] ===== _do_start_strategy 开始 ====="
            f"\n  入参 worker_id={worker_id} (type={type(worker_id).__name__})"
            f"\n  入参 worker.id={worker.id} (type={type(worker.id).__name__})"
            f"\n  入参 worker.name={worker.name}"
        )

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            logger.warning(f"[StrategyManager] Worker {worker_id} 不在注册表中")
            return False

        if runtime.is_running:
            raise WorkerAlreadyRunningException(worker_id)

        # 获取交易所配置
        exchange = getattr(worker, "exchange", "binance") or "binance"
        if hasattr(exchange, "value"):
            exchange = exchange.value

        trading_mode = getattr(worker, "trading_mode", "testnet") or "testnet"
        if hasattr(trading_mode, "value"):
            trading_mode = trading_mode.value

        # 创建日志目录
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        log_directory = os.path.join(backend_dir, "logs", "worker")
        os.makedirs(log_directory, exist_ok=True)

        # 加载策略
        try:
            from backtest.strategy_loader_service import StrategyLoaderService
            from strategy.models import Strategy

            # 关联的策略对象
            strategy = getattr(worker, "strategy", None)
            if strategy is None and db is not None:
                strategy = db.query(Strategy).filter(Strategy.id == worker.strategy_id).first()

            if strategy is None:
                msg = f"无法找到 worker {worker_id} 关联的策略"
                raise ValueError(msg)

            # 解析交易配置，获取品种和时间周期
            trading_config = worker.get_trading_config_dict() if hasattr(worker, "get_trading_config_dict") else {}
            symbols = worker.get_symbols() if hasattr(worker, "get_symbols") else []
            timeframe = trading_config.get("timeframe", "1h")

            if not symbols:
                msg = f"worker {worker_id} 未配置交易品种"
                raise ValueError(msg)

            # 解析策略参数
            params = {}
            if strategy.parameters:
                try:
                    raw_params = (
                        json.loads(strategy.parameters) if isinstance(strategy.parameters, str) else strategy.parameters
                    )
                    if isinstance(raw_params, dict):
                        params = raw_params
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"[StrategyManager] 策略参数 JSON 解析失败: {e}")

            # RL 策略不走 StrategyLoaderService（那里只加载规则 / LLM 策略源码）：
            # 模型与观测规格直接注册到统一内核 / LiveDriver 的 RL host
            if (getattr(strategy, "strategy_type", None) or "rule") == "rl":
                rl_mode = trading_config.get("trading_mode", trading_mode)
                if rl_mode == "live":
                    # 实盘闸门（设计文档 9.4）：testnet 对账通过前不放行主网
                    msg = f"worker {worker_id} 配置了 RL 主网实盘（live），主网闸门尚未开放，请先使用 testnet 模式"
                    raise ValueError(msg)
                market_type = trading_config.get("market_type", "spot")
                if rl_mode == "testnet":
                    self.start_rl_live(worker_id, params, timeframe, symbols, exchange, market_type)
                elif rl_mode == "paper":
                    self.start_rl_paper(worker_id, params, timeframe, symbols, exchange, market_type)
                else:
                    msg = (
                        f"worker {worker_id} 的 RL 策略 trading_mode={rl_mode} 不支持，"
                        "可选: paper（模拟盘）/ testnet（合约测试网实盘）"
                    )
                    raise ValueError(msg)
                await self._finalize_start(worker_id, runtime, db)
                logger.info(f"[StrategyManager] RL 循环已启动: worker_id={worker_id}, mode={rl_mode}")
                return True

            # 通过策略加载器加载策略（唯一路径：load_strategy → BaseStrategy）
            # paper/live 的 LLM 策略在这里被包成 RecordingProvider（回测则由
            # engine_service 传 run_mode="backtest" 走 replay）
            strategy_instance = StrategyLoaderService.load_strategy(
                strategy_name=strategy.strategy_name or strategy.name,
                strategy_params=params,
                instrument_ids=symbols,
                bar_types=[timeframe],
                run_mode="live" if trading_mode == "live" else "paper",
            )
        except Exception as e:
            logger.error(f"[StrategyManager] 策略加载失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}")
            # 加载失败直接抛出，由 start_strategy 的异常处理统一上报 worker error 状态
            raise

        logger.info(
            f"[StrategyManager] 策略已加载: worker_id={worker_id}, strategy_class={type(strategy_instance).__name__}"
        )

        # 获取交易对符号
        symbol = getattr(worker, "symbol", "BTCUSDT") or "BTCUSDT"

        # 构建 exchange adapter（按 trading_mode 选择真实/paper 实现）
        try:
            adapter = _build_exchange_adapter(exchange, trading_mode)
            logger.info(
                f"[StrategyManager] Exchange adapter 已构建: "
                f"worker_id={worker_id}, exchange={exchange}, "
                f"trading_mode={trading_mode}, adapter_type={type(adapter).__name__}"
            )
        except Exception as e:
            logger.error(
                f"[StrategyManager] 构建 exchange adapter 失败: "
                f"worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            raise

        # 解析因子列表：支持 params.factor_names（列表）或 params.factor_name（单个）
        factor_names = []
        raw_factor_names = params.get("factor_names")
        if isinstance(raw_factor_names, list) and raw_factor_names:
            factor_names = [str(f) for f in raw_factor_names if f]
        elif isinstance(params.get("factor_name"), str) and params["factor_name"]:
            factor_names = [params["factor_name"]]

        # 创建策略循环
        strategy_loop = StrategyLoop(
            adapter=adapter,
            strategy=strategy_instance,
            symbol=symbol,
            factor_names=factor_names,
            timeframe=timeframe,
        )

        # 保存策略循环引用
        self._strategy_loops[worker_id] = strategy_loop

        # 启动策略循环（在独立线程中）
        try:
            strategy_loop.start()
        except Exception as e:
            logger.error(
                f"[StrategyManager] 启动策略循环失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            raise

        # 统一收尾：注册表 / DB / worker_state 三处状态流转
        await self._finalize_start(worker_id, runtime, db)

        logger.info(f"[StrategyManager] 策略已启动: worker_id={worker_id}")
        return True

    async def _finalize_start(self, worker_id: int, runtime, db=None) -> None:
        """启动成功后的统一收尾：注册表 / DB / worker_state 三处状态流转。

        规则策略与 RL 实盘两条启动路径共用，避免各写一份后漂移。
        """
        from .state import strategy_registry

        strategy_registry.update_status(worker_id, "running")

        runtime.set_pid(os.getpid())

        if runtime.started_at is None:
            runtime.started_at = datetime.now(UTC).isoformat()

        if db is not None:
            crud.update_worker_status(db, worker_id, "running", pid=os.getpid())
            db.commit()

        await worker_state_manager.transition(worker_id, "running")

    def _load_rl_spec(self, worker_id: int, params: dict[str, Any]) -> dict[str, Any]:
        """加载 RL 模型并整理推理回调 + 观测规格（回测内核 / LiveDriver 共用）。

        校验链：model_path 存在 → 观测规格元数据存在 → spec_version 匹配 → 模型可加载。

        Returns:
            dict：predict / model_id / spec_version / window_size / features /
            action_space / stats，调用方按序传入 add_rl_strategy 即可。

        Raises:
            ValueError: 模型文件缺失、缺少观测规格元数据、`spec_version` 不匹配，
                或原生扩展 / SB3 不可用。调用方必须按启动失败处理，不能回退到规则策略。
        """
        from services.rl_service import (
            KERNEL_ACTION_SPACE,
            KERNEL_FEATURES,
            KERNEL_SPEC_VERSION,
            KERNEL_WINDOW_SIZE,
            RLService,
            make_predict_fn,
            observation_stats_from_meta,
            rl_meta_path,
        )

        model_path = str(params.get("model_path") or "").strip()
        if not model_path:
            msg = f"worker {worker_id} 的 RL 策略缺少 model_path 参数"
            raise ValueError(msg)
        if not os.path.isfile(model_path):
            msg = f"RL 模型文件不存在: {model_path}"
            raise ValueError(msg)

        meta_file = rl_meta_path(model_path)
        if not meta_file.is_file():
            msg = f"RL 模型缺少观测规格元数据，无法校验口径: {meta_file}"
            raise ValueError(msg)
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

        requested_spec = str(params.get("spec_version") or KERNEL_SPEC_VERSION)
        if meta.get("spec_version") != requested_spec:
            msg = f"RL 模型 spec_version 不匹配: 模型={meta.get('spec_version')} 期望={requested_spec}"
            raise ValueError(msg)

        model = RLService().load_model(model_path)
        if model is None:
            msg = f"无法加载 RL 模型: {model_path}"
            raise ValueError(msg)

        return {
            "predict": make_predict_fn(model),
            "model_id": str(meta.get("model_id") or Path(model_path).stem),
            "spec_version": requested_spec,
            "window_size": int(meta.get("window_size") or KERNEL_WINDOW_SIZE),
            "features": meta.get("features") or KERNEL_FEATURES,
            "action_space": KERNEL_ACTION_SPACE,
            # 训练期归一化统计量：缺了内核 Z-Score 恒为 0，与训练分布不一致
            "stats": observation_stats_from_meta(meta, model_path=model_path),
        }

    def build_rl_kernel(
        self,
        worker_id: int,
        params: dict[str, Any],
        timeframe: str,
        symbols: list[str],
    ):
        """校验 RL 模型并把推理回调注册到统一内核的 RL host（回测用）。

        只做「构造 + 注册」：内核需要逐 bar 数据驱动才能跑。实时驱动已改走
        `start_rl_live`（LiveDriver），本方法保留给回测 / 后续 pump 接入复用。

        Args:
            worker_id: Worker ID（用于缓存 kernel 与日志）
            params: 策略参数，需含 `model_path`；可选 `spec_version` / `initial_capital`
            timeframe: K 线周期（内核据此推导收市时刻）
            symbols: 交易品种列表，RL host 只挂第一个

        Returns:
            已装配 RL host 的 `worker.Kernel`
        """
        # 延迟导入：原生扩展与 RL 服务都是可选重依赖
        from axon_quant import worker as axon_worker

        from services.rl_service import RL_TRANSACTION_COST
        from strategy.rust_adapter import _normalize_symbol

        spec = self._load_rl_spec(worker_id, params)

        symbol = symbols[0]
        kernel = axon_worker.Kernel(
            initial_cash=float(params.get("initial_capital", 100_000.0)),
            interval=timeframe,
            # 费率与 RL 训练环境同源：常量只在 `services.rl_service` 定义一次，
            # 这里 import 复用，避免两处各写一个数字后悄悄漂移
            fee_rate=RL_TRANSACTION_COST,
        )
        kernel.add_rl_strategy(
            spec["predict"],
            spec["model_id"],
            spec["spec_version"],
            spec["window_size"],
            spec["features"],
            spec["action_space"],
            _normalize_symbol(symbol),
            stats=spec["stats"],
        )
        self._rl_kernels[worker_id] = kernel

        logger.info(
            f"[StrategyManager] RL host 已注册: worker_id={worker_id}, "
            f"model_id={spec['model_id']}, spec_version={spec['spec_version']}, symbol={symbol}"
        )
        return kernel

    def start_rl_live(
        self,
        worker_id: int,
        params: dict[str, Any],
        timeframe: str,
        symbols: list[str],
        exchange: str,
        market_type: str,
    ) -> dict[str, Any]:
        """装配 RL 实盘 LiveDriver 并启动逐 tick 驱动线程（testnet）。

        构造过程不联网（connect 在驱动线程里做），配置 / 凭证 / 模型问题
        直接抛 ValueError，由调用方按启动失败上报。

        v1 边界：仅 Binance USDT-M 永续 testnet（spot 不支持、主网闸门未开，
        见设计文档 9.4）。

        Args:
            worker_id: Worker ID（用于运行态缓存与 journal 定位）
            params: 策略参数，需含 `model_path` / `credentials_account`；
                可选 `spec_version` / `initial_capital`
            timeframe: K 线周期（驱动 bar 闭合节奏）
            symbols: 交易品种列表，RL host 只挂第一个
            exchange: 交易所标识（v1 仅 binance）
            market_type: 市场类型（v1 仅 swap/futures）

        Returns:
            运行态 dict：{driver, stop_event, thread, journal_path}
        """
        from axon_quant import worker as axon_worker
        from axon_quant.exchange import ExchangeConfig, ExchangeId

        from credentials.service import CredentialsService
        from services.rl_service import RL_TRANSACTION_COST
        from strategy.rust_adapter import _normalize_symbol

        if exchange.lower() != "binance":
            msg = f"worker {worker_id} RL 实盘暂只支持 binance，当前配置: {exchange}"
            raise ValueError(msg)
        if market_type not in ("swap", "futures"):
            msg = (
                f"worker {worker_id} RL 实盘 v1 仅支持永续合约（swap/futures），"
                f"当前 market_type={market_type}，spot 暂不支持"
            )
            raise ValueError(msg)

        account_name = str(params.get("credentials_account") or "").strip()
        if not account_name:
            msg = (
                f"worker {worker_id} RL 实盘需要在策略参数中配置 "
                "credentials_account（凭证管理中的账户名），不支持从环境变量隐式取 key"
            )
            raise ValueError(msg)

        api_key, api_secret = CredentialsService().get_credential(account_name)

        # binance_testnet_config() 硬编码的是现货测试网 URL，而 LiveDriver v1
        # 只支持合约 → 这里手工构造 USDT-M 合约测试网配置
        # （URL 与 exchange/binance/exchange.py 的既有 testnet 路径一致）
        config = ExchangeConfig(
            exchange_id=ExchangeId.Binance,
            api_key=api_key,
            api_secret=api_secret,
            rest_base_url="https://testnet.binancefuture.com",
            ws_url="wss://stream.binancefuture.com/ws",
            testnet=True,
        )

        driver = axon_worker.LiveDriver(
            config,
            [_normalize_symbol(s) for s in symbols],
            initial_cash=float(params.get("initial_capital", 100_000.0)),
            interval=timeframe,
            # 费率与 RL 训练环境同源（services.rl_service 唯一定义）
            fee_rate=RL_TRANSACTION_COST,
        )

        spec = self._load_rl_spec(worker_id, params)
        driver.add_rl_strategy(
            spec["predict"],
            spec["model_id"],
            spec["spec_version"],
            spec["window_size"],
            spec["features"],
            spec["action_space"],
            _normalize_symbol(symbols[0]),
            stats=spec["stats"],
        )

        journal_path = self._rl_live_journal_path(worker_id)
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._rl_live_thread_main,
            args=(worker_id, driver, journal_path, stop_event),
            daemon=True,
            name=f"rl-live-{worker_id}",
        )
        thread.start()
        live = {
            "driver": driver,
            "stop_event": stop_event,
            "thread": thread,
            "journal_path": journal_path,
        }
        self._rl_live[worker_id] = live

        logger.info(
            f"[StrategyManager] RL LiveDriver 已装配: worker_id={worker_id}, "
            f"symbols={symbols}, interval={timeframe}, journal={journal_path}"
        )
        return live

    def _rl_live_thread_main(
        self,
        worker_id: int,
        driver: Any,
        journal_path: str,
        stop_event: threading.Event,
    ) -> None:
        """RL 实盘驱动线程：connect → resume/start → 1s 轮询 tick。

        线程内没有调用方可接异常，连接失败统一降级为 worker error 状态
        （registry + DB），线程自身退出；单次 tick 异常只记日志继续。
        """
        journal = Path(journal_path)
        try:
            driver.connect()
            if journal.is_file() and journal.stat().st_size > 0:
                # 崩溃恢复：重演 journal + 对账，报告仅记日志
                report = driver.resume(str(journal))
                logger.info(f"[StrategyManager] RL 实盘恢复完成: worker_id={worker_id}, report={report}")
            else:
                driver.start(str(journal))
        except Exception as e:
            logger.error(
                f"[StrategyManager] RL 实盘连接/恢复失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            self._mark_rl_live_error(worker_id, f"RL 实盘连接/恢复失败: {e}")
            return

        logger.info(f"[StrategyManager] RL 实盘 tick 循环启动: worker_id={worker_id}")
        while not stop_event.is_set():
            try:
                driver.tick()
            except Exception as e:
                logger.error(f"[StrategyManager] RL 实盘 tick 异常: worker_id={worker_id}, error={e}")
            # wait 而非 sleep：stop 可即时唤醒（与 StrategyLoop 同风格）
            stop_event.wait(1.0)

        logger.info(f"[StrategyManager] RL 实盘 tick 循环退出: worker_id={worker_id}")

    def start_rl_paper(
        self,
        worker_id: int,
        params: dict[str, Any],
        timeframe: str,
        symbols: list[str],
        exchange: str,
        market_type: str,
    ) -> dict[str, Any]:
        """装配 RL paper 模拟盘 PaperDriver 并启动逐 bar 驱动线程。

        与 start_rl_live 同闸门（仅 binance 永续），差异：
        - 无需凭证：撮合走 PaperSink 内置盘口种子，不连真实账户
        - 行情走 testnet 公共 REST 轮询（收市 K 线），而非 WS 实时推送

        Args:
            worker_id: Worker ID（用于运行态缓存与日志）
            params: 策略参数，需含 `model_path`；可选 `spec_version` / `initial_capital`
            timeframe: K 线周期（决定轮询节拍与 REST interval 参数）
            symbols: 交易品种列表，RL host 只挂第一个
            exchange: 交易所标识（v1 仅 binance）
            market_type: 市场类型（v1 仅 swap/futures）

        Returns:
            运行态 dict：{driver, stop_event, thread}（paper 无 journal，不做崩溃恢复）
        """
        from axon_quant import worker as axon_worker

        from services.rl_service import RL_TRANSACTION_COST
        from strategy.rust_adapter import _normalize_symbol

        if exchange.lower() != "binance":
            msg = f"worker {worker_id} RL paper 暂只支持 binance，当前配置: {exchange}"
            raise ValueError(msg)
        if market_type not in ("swap", "futures"):
            msg = (
                f"worker {worker_id} RL paper v1 仅支持永续合约（swap/futures），"
                f"当前 market_type={market_type}，spot 暂不支持"
            )
            raise ValueError(msg)
        if timeframe not in _RL_PAPER_INTERVAL_SECONDS:
            msg = (
                f"worker {worker_id} RL paper 不支持时间周期 {timeframe}，"
                f"支持: {sorted(_RL_PAPER_INTERVAL_SECONDS)}"
            )
            raise ValueError(msg)

        spec = self._load_rl_spec(worker_id, params)

        driver = axon_worker.PaperDriver(
            [_normalize_symbol(s) for s in symbols],
            initial_cash=float(params.get("initial_capital", 100_000.0)),
            # 费率与 RL 训练环境同源（services.rl_service 唯一定义）
            fee_rate=RL_TRANSACTION_COST,
            interval=timeframe,
        )
        driver.add_rl_strategy(
            spec["predict"],
            spec["model_id"],
            spec["spec_version"],
            spec["window_size"],
            spec["features"],
            spec["action_space"],
            _normalize_symbol(symbols[0]),
            stats=spec["stats"],
        )

        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._rl_paper_thread_main,
            args=(
                worker_id,
                driver,
                timeframe,
                [_normalize_symbol(s) for s in symbols],
                spec["window_size"],
                stop_event,
            ),
            daemon=True,
            name=f"rl-paper-{worker_id}",
        )
        thread.start()
        paper = {"driver": driver, "stop_event": stop_event, "thread": thread}
        self._rl_live[worker_id] = paper

        logger.info(
            f"[StrategyManager] RL PaperDriver 已装配: worker_id={worker_id}, "
            f"symbols={symbols}, interval={timeframe}"
        )
        return paper

    def _rl_paper_thread_main(
        self,
        worker_id: int,
        driver: Any,
        timeframe: str,
        symbols: list[str],
        window_size: int,
        stop_event: threading.Event,
    ) -> None:
        """RL paper 驱动线程：start → 睡到收市点 → 拉收市 K 线喂 driver。

        与 _rl_live_thread_main 一样线程内自兜底：启动失败降级 worker error，
        单轮拉取/喂单异常只记日志继续。停机的 driver.shutdown 由 stop_strategy
        统一做（线程退出后才能安全 shutdown）。
        """
        step_s = _RL_PAPER_INTERVAL_SECONDS.get(timeframe, 60)
        try:
            driver.start()
        except Exception as e:
            logger.error(
                f"[StrategyManager] RL paper 启动失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            self._mark_rl_live_error(worker_id, f"RL paper 启动失败: {e}")
            return

        logger.info(f"[StrategyManager] RL paper 循环启动: worker_id={worker_id}, interval={timeframe}")
        # 首轮多拉几根把 RL 观测窗口补满；之后只拉最近 2 根防窗口重叠
        limit = window_size + 2
        seen_open_ms: dict[str, int] = {}
        while not stop_event.is_set():
            try:
                self._rl_paper_pump_round(worker_id, driver, symbols, timeframe, seen_open_ms, limit)
                limit = 2
            except Exception as e:
                logger.error(f"[StrategyManager] RL paper 拉取/喂单异常: worker_id={worker_id}, error={e}")
                # ponytail: 连续失败跨多根 K 线会漏 bar（下轮 limit=2 补不回更早的），
                # paper 演练可接受；彻底解法按 seen 与当前时间差值动态拉取
            # wait 而非 sleep：stop 可即时唤醒；+0.5s 缓冲等交易所端收市 K 线就绪
            stop_event.wait(step_s - (time.time() % step_s) + 0.5)

        logger.info(f"[StrategyManager] RL paper 循环退出: worker_id={worker_id}")

    def _rl_paper_pump_round(
        self,
        worker_id: int,
        driver: Any,
        symbols: list[str],
        timeframe: str,
        seen_open_ms: dict[str, int],
        limit: int,
    ) -> None:
        """拉一轮收市 K 线并注入 driver，全部喂完后 tick 一次。

        已收市判定用 open_ms + step_ms <= now（不信任交易所 closeTime 的 -1ms
        惯例）；按开市时间去重，REST 窗口重叠时不会重复喂同一根 bar。
        抽成独立方法：线程循环只负责节拍，这份核心逻辑可在测试中同步直调。
        """
        step_ms = _RL_PAPER_INTERVAL_SECONDS[timeframe] * 1000
        now_ms = int(time.time() * 1000)
        for symbol in symbols:
            api_symbol = symbol.replace("/", "")  # BTC/USDT → BTCUSDT
            for row in self._rl_paper_fetch_klines(api_symbol, timeframe, limit):
                open_ms = int(row[0])
                if open_ms + step_ms > now_ms:
                    continue  # 未收市的最新 K 线不喂（决策只用收盘确认价）
                if open_ms <= seen_open_ms.get(api_symbol, 0):
                    continue
                seen_open_ms[api_symbol] = open_ms
                # feed_bar 吃开市时刻纳秒，事件时间戳由引擎按 interval 推成收市时刻
                driver.feed_bar(
                    symbol,
                    open_ms * 1_000_000,
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                    float(row[4]),
                    float(row[5]),
                )
        driver.tick()

    def _rl_paper_fetch_klines(self, api_symbol: str, timeframe: str, limit: int) -> list[list]:
        """拉 binance USDT-M testnet 公共收市 K 线（不签名）。

        ponytail: 标准库 urlopen 就够（一次 GET + timeout）；requests 未在
        pyproject 声明为直接依赖（只是 python-binance 的传递依赖），不为一次
        调用把它升级成直接依赖。symbol/timeframe 均来自白名单受限字符集，
        URL 无需额外编码。

        Returns:
            binance 原始行：[openTime, open, high, low, close, volume, ...]（数值是字符串）
        """
        url = f"{_RL_PAPER_KLINES_URL}?symbol={api_symbol}&interval={timeframe}&limit={limit}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _mark_rl_live_error(self, worker_id: int, message: str) -> None:
        """把 RL 循环（live/paper）运行失败落到 registry + DB 的 error 状态。

        线程内的失败没有启动调用方兜底，必须自带上报；DB 写失败不影响降级结果。
        """
        from .state import strategy_registry

        strategy_registry.update_status(worker_id, "error", error_message=message)
        try:
            with get_db_session() as db:
                crud.update_worker_status(db, worker_id, "error")
                db.commit()
        except Exception as e:
            logger.error(f"[StrategyManager] RL 循环错误状态落库失败: worker_id={worker_id}, error={e}")

    def _rl_live_journal_path(self, worker_id: int) -> str:
        """RL 实盘 journal 文件路径：backend/data/rl_live/worker_{id}.jsonl。

        journal 驱动 resume 对账，进程重启后据此恢复持仓与资金状态。
        """
        data_dir = os.environ.get("QUANTCELL_DATA_DIR")
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "data"
        rl_live_dir = base / "rl_live"
        rl_live_dir.mkdir(parents=True, exist_ok=True)
        return str(rl_live_dir / f"worker_{worker_id}.jsonl")

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
            logger.info(f"[StrategyManager] Worker {worker_id} 已经处于 stopped 状态")
            return True

        await worker_state_manager.transition(worker_id, "stopping")

        # 停止策略循环
        strategy_loop = self._strategy_loops.get(worker_id)
        if strategy_loop is not None:
            try:
                strategy_loop.stop()
            except Exception as e:
                logger.error(f"[StrategyManager] 停止策略循环失败: worker_id={worker_id}, error={e}")
            del self._strategy_loops[worker_id]

        # RL live/paper：先通知停驱动线程并等待退出，再收口 driver
        # （线程退出前 driver 仍被循环使用，必须先 join 才能安全 shutdown）
        live = self._rl_live.pop(worker_id, None)
        if live is not None:
            live["stop_event"].set()
            live["thread"].join(timeout=5)
            if live["thread"].is_alive():
                logger.error(f"[StrategyManager] RL 循环线程未能在 5s 内停止: worker_id={worker_id}")
            try:
                live["driver"].shutdown()
            except Exception as e:
                logger.error(f"[StrategyManager] RL driver 关闭失败: worker_id={worker_id}, error={e}")

        # RL 回测 kernel 不持有线程，丢掉引用即可
        self._rl_kernels.pop(worker_id, None)

        runtime.stopped_at = datetime.now(UTC).isoformat()
        strategy_registry.update_status(worker_id, "stopped")

        try:
            with get_db_session() as db:
                crud.update_worker_status(db, worker_id, "stopped")
                db.commit()
        except Exception as e:
            logger.error(f"[StrategyManager] 更新数据库状态失败: worker_id={worker_id}, error={e}")

        await worker_state_manager.transition(worker_id, "stopped")

        logger.info(f"[StrategyManager] 策略已停止: worker_id={worker_id}")
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
            logger.error(f"[StrategyManager] 删除策略失败: worker_id={worker_id}, error={e}")
            return False

        logger.info(f"[StrategyManager] 策略已删除: worker_id={worker_id}")
        return True

    def get_strategy_state(self, worker_id: int) -> dict[str, Any] | None:
        """获取策略运行时状态"""
        from .state import strategy_registry

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            return None
        return runtime.to_dict()

    def list_strategies(self) -> list[dict[str, Any]]:
        """列出所有策略摘要"""
        from .state import strategy_registry

        return [rt.to_dict() for rt in strategy_registry.list_all()]

    def get_system_state(self) -> dict[str, Any]:
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

    def get_summary(self) -> dict[str, Any]:
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

    def engine_status(self) -> dict[str, Any]:
        """获取引擎状态概览（兼容 TradingEngine API）"""
        from .state import strategy_registry

        strategies = strategy_registry.list_all()
        running_count = sum(1 for s in strategies if s.status == "running")
        return {
            "exchange": "binance",
            "mode": "paper",
            "exchange_connected": True,
            "risk_available": True,
            "total_strategies": len(strategies),
            "running_strategies": running_count,
        }

    def get_strategy_status(self, strategy_id: str) -> dict[str, Any] | None:
        """获取策略状态（兼容 TradingEngine API，支持 string ID）"""
        from .state import strategy_registry

        # 支持 string 和 int 类型的 strategy_id
        try:
            worker_id = int(strategy_id)
        except ValueError:
            worker_id = strategy_id

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            # 尝试按名称查找
            for rt in strategy_registry.list_all():
                if rt.name == strategy_id or str(rt.worker_id) == strategy_id:
                    return rt.to_dict()
            return None
        return runtime.to_dict()

    def register_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        mode: str = "paper",
    ) -> str:
        """注册策略（内存级别，无持久化，兼容 TradingEngine API）"""
        from .state import StrategyRuntime, strategy_registry

        # 生成临时 worker_id
        temp_id = hash((id(strategy), time.monotonic())) % 1000000
        runtime = StrategyRuntime(
            worker_id=temp_id,
            strategy_id=0,
            name=strategy_name or strategy.__class__.__name__,
            strategy=strategy,
            symbols=list(symbols),
            params=params or {},
            mode=mode,
        )
        strategy_registry.register(runtime)

        logger.info(f"[StrategyManager] 策略已注册: {temp_id} {symbols}")
        return str(temp_id)

    def shutdown(self) -> None:
        """关闭系统，释放资源"""
        start_time = time.monotonic()
        logger.info("[StrategyManager] ========== shutdown 开始 ==========")

        from .state import strategy_registry

        strategies = strategy_registry.list_all()
        logger.info(
            f"[StrategyManager] shutdown: 共 {len(strategies)} 个策略, "
            f"其中运行中 {sum(1 for s in strategies if s.is_running)} 个"
        )

        # 停止所有策略循环
        for worker_id, strategy_loop in self._strategy_loops.items():
            try:
                strategy_loop.stop()
                logger.info(f"[StrategyManager] shutdown: worker_id={worker_id} 策略循环已停止")
            except Exception as e:
                logger.warning(f"[StrategyManager] shutdown: worker_id={worker_id} 停止策略循环失败: {e}")

        self._strategy_loops.clear()

        # 停掉 RL 实盘驱动线程并收口 driver
        for worker_id, live in self._rl_live.items():
            try:
                live["stop_event"].set()
                live["thread"].join(timeout=5)
                if live["thread"].is_alive():
                    logger.warning(f"[StrategyManager] shutdown: worker_id={worker_id} RL 实盘线程未在 5s 内停止")
                live["driver"].shutdown()
                logger.info(f"[StrategyManager] shutdown: worker_id={worker_id} RL 实盘已停止")
            except Exception as e:
                logger.warning(f"[StrategyManager] shutdown: worker_id={worker_id} 停止 RL 实盘失败: {e}")
        self._rl_live.clear()

        self._rl_kernels.clear()

        # 关闭线程池
        logger.info("[StrategyManager] shutdown: 开始关闭 ThreadPoolExecutor...")
        self._executor.shutdown(wait=False)

        elapsed = time.monotonic() - start_time
        logger.info(
            f"[StrategyManager] shutdown: 总耗时 {elapsed:.3f}s\n[StrategyManager] ========== shutdown 完成 =========="
        )


# =============================================================================
# 模块级单例：worker_system 供 lifespan 和其他模块直接导入使用
# =============================================================================

worker_system = StrategyManager()


def _register_to_state() -> None:
    """将实例注册到 state.py 的全局单例"""
    import worker.state as _state

    if _state.strategy_manager is None:
        _state.strategy_manager = worker_system
        logger.info("[StrategyManager] 已注册到 state.py 单例枢纽")


_register_to_state()
