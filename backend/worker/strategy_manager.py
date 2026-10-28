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

from axon_quant import worker as axon_worker

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

from . import crud
from .exceptions import (
    WorkerAlreadyRunningException,
    WorkerNotFoundException,
)
from .live_trade_sync import LIVE_TRADE_SYNC_INTERVAL_S, LiveTradeSync
from .log_utils import append_worker_error_log, start_worker_log_sink, stop_worker_log_sink
from .paper_trade_sync import PaperTradeSync
from .risk_config import RiskPnlFeeder, apply_risk_config
from .worker_state import worker_state_manager

logger = get_logger(__name__, LogType.APPLICATION)

# paper 行情泵支持的 K 线周期 → 周期秒数（与 exchange/base.py 的 interval 映射同口径；
# 键同时作为 binance REST 的 interval 参数，周期外直接在装配期拒绝）
_PAPER_INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# paper 行情泵轮询端点：testnet 公共 K 线，不签名、无需凭证
_PAPER_KLINES_URL = "https://testnet.binancefuture.com/fapi/v1/klines"

# live tick 线程节拍与 snapshot 轮询推送窗口（Driver 无逐笔查询口，轮询是唯一观测口）
_LIVE_TICK_INTERVAL_S = 1.0
_LIVE_SNAPSHOT_INTERVAL_S = 15.0

# 轮询强制直连：urllib 默认读 macOS/GUI 代理工具注册的系统代理（如 127.0.0.1:7897），
# 代理不在线时整个轮询管线收不到任何 bar；同链路的 requests/python-binance 只读
# 环境变量故直连可达，这里显式清掉代理保持同一语义
_PAPER_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _resolve_live_credentials(worker_id: int, exchange: str, params: dict[str, Any]) -> tuple[str, str]:
    """解析 live/testnet 装配所需凭证，返回 (api_key, api_secret)。

    系统里有两套互不相通的凭证体系：
    1. 「凭证管理」CredentialsService —— CLI `quantcell account add` 创建，
       机器指纹加密存储（credentials.db）。显式路径：策略参数 credentials_account。
    2. 「系统配置」SystemConfig 表 —— 前端设置页保存的
       `exchange.{exchange}.testnet_api_key / testnet_api_secret`
       （与「测试连接」按钮、行情采集同源）。

    显式账户优先；缺 credentials_account 时回退读系统配置的测试网 Key，
    让只在 GUI 里配过 Key 的用户也能启动 testnet worker。两者皆无才报错，
    报错信息同时指引两个配置来源。
    """
    # credentials 模块带机器指纹加密与独立 SQLite，属可选组件；worker 会被
    # 回测 / CLI / 迁移脚本等多种入口导入，函数内导入避免把该依赖强加给所有调用方
    from credentials.exceptions import AccountNotFoundError
    from credentials.service import CredentialsService

    account_name = str(params.get("credentials_account") or "").strip()
    if account_name:
        try:
            return CredentialsService().get_credential(account_name)
        except AccountNotFoundError as e:
            # 显式指定的账户不存在：报错里带出两个可用配置来源，方便用户纠偏
            raise ValueError(
                f"worker {worker_id} 凭证管理中不存在账户 {account_name!r}；"
                "可在策略参数中改配已存在的 credentials_account，"
                f"或使用系统配置中 {exchange} 的测试网 API Key"
            ) from e

    # 回退路径：读系统配置里该交易所的测试网 Key（与 market_data_factory 同口径）。
    # settings.models 顶层导入会拉起 DB 元数据并与 worker 存在环形导入风险，保持函数内导入；
    # 无 DB / 未配置等任何异常都视为「系统配置无可用凭证」，走末尾报错分支
    config_map: dict[str, Any] = {}
    try:
        from settings.models import SystemConfigBusiness

        prefix = f"exchange.{exchange}."
        config_map = {
            key[len(prefix) :]: value for key, value in SystemConfigBusiness.get_all().items() if key.startswith(prefix)
        }
    except Exception:  # ponytail: 配置读取失败统一按未配置处理，报错走统一出口
        config_map = {}

    api_key = str(config_map.get("testnet_api_key") or "").strip()
    api_secret = str(config_map.get("testnet_api_secret") or "").strip()
    if api_key and api_secret:
        return api_key, api_secret

    raise ValueError(
        f"worker {worker_id} 实盘未找到可用凭证："
        "① 在策略参数中配置 credentials_account（凭证管理中的账户名，"
        "CLI: quantcell account add），"
        f"或 ② 在系统配置页面保存 {exchange} 的测试网 API Key/Secret"
        "（exchange.{exchange}.testnet_api_key / testnet_api_secret）"
    )


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
        # RL 策略已装配但尚未被数据泵驱动的内核（worker_id → worker.Kernel）
        self._rl_kernels: dict[int, Any] = {}
        # driver 运行态缓存（worker_id → {driver, stop_event, thread, journal_path?}）：
        # 规则/LLM paper、RL paper、RL live 三类运行共用，停机统一走 stop_strategy；
        # live 额外带 journal_path，paper 无持久化
        self._kernel_runs: dict[int, dict[str, Any]] = {}
        logger.info(f"[StrategyManager] ThreadPoolExecutor 初始化: max_workers={max_workers}")

    async def initialize(self) -> None:
        """初始化系统，从数据库恢复策略状态"""
        async with self._lock:
            if self._initialized:
                return
            self._initialized = True

        logger.info("[StrategyManager] 正在初始化...")

        # Rust 引擎 WARN+ 日志桥接到 Python logging：live 链路 Rust 侧风险告警
        # （订单被拒、断线重连等）在 Python 日志面可见。幂等安装，失败仅降级
        # （Rust 告警不可见），不阻断初始化——桥自身静默失败返回 bool，不抛异常
        if axon_worker.install_rust_logging():
            logger.info("[StrategyManager] Rust 日志桥已安装（WARN+ 转发至 axon_quant.rust logger）")
        else:
            logger.warning(
                "[StrategyManager] Rust 日志桥安装未生效（可能已被其他 subscriber 抢占），Rust 侧告警将不可见"
            )

        await worker_state_manager.initialize()

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
                        # 补第三层（缓存 + WS 广播 + DB 持久化一并完成）：本方法在
                        # async 上下文，可直接 await；失败仅记日志不中断本轮恢复。
                        # 变量用 te：内层 except 结束后 Python 会 del e，不能覆盖外层的 e
                        try:
                            await worker_state_manager.transition(worker.id, "error", error_message=error_msg)
                        except Exception as te:
                            logger.error(
                                f"[StrategyManager] 恢复校验失败状态同步异常: worker_id={worker.id}, error={te}"
                            )
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
                        # 补第三层（缓存 + WS 广播 + DB 持久化）：重启恢复失败也要让
                        # 缓存与 WS 立即变 error，否则前端仍显示「运行中」
                        try:
                            await worker_state_manager.transition(worker.id, "error", error_message=str(e))
                        except Exception as te:
                            logger.error(f"[StrategyManager] 恢复失败状态同步异常: worker_id={worker.id}, error={te}")
                        # 恢复失败同样发生在 sink 挂载前，手动双写让前端日志 tab 可见
                        append_worker_error_log(worker.id, f"恢复启动失败: {e}")

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
            # 启动失败的异常发生在 per-worker 日志 sink 挂载之前，全局日志前端看不到；
            # 手动写入 per-worker 通道（文件 + 内存环），详情页日志 tab / 头部才能看到原因
            append_worker_error_log(worker_id, f"启动失败: {e}")
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
        from .state import StrategyRuntime, strategy_registry

        logger.info(
            f"[StrategyManager] ===== _do_start_strategy 开始 ====="
            f"\n  入参 worker_id={worker_id} (type={type(worker_id).__name__})"
            f"\n  入参 worker.id={worker.id} (type={type(worker.id).__name__})"
            f"\n  入参 worker.name={worker.name}"
        )

        runtime = strategy_registry.get(worker_id)
        if runtime is None:
            # 直调路径（core_service 进程内启动）在 lifespan 全量注册之后创建的
            # worker 不在注册表中（create_worker 只落 DB），此处兜底注册，
            # 口径与 _load_workers_from_db 一致
            runtime = StrategyRuntime(
                worker_id=worker.id,
                strategy_id=worker.strategy_id,
                name=worker.name or f"worker-{worker.id}",
                status="stopped",
            )
            strategy_registry.register(runtime)
            logger.info(f"[StrategyManager] Worker {worker.id} 未在注册表中，已兜底注册后继续启动")

        if runtime.is_running:
            raise WorkerAlreadyRunningException(worker_id)

        # 获取交易所配置
        exchange = getattr(worker, "exchange", "binance") or "binance"
        if hasattr(exchange, "value"):
            exchange = exchange.value

        # 兜底取 paper：与 schemas.TradingConfig.trading_mode 默认值一致（此前兜底 testnet
        # 会让未显式配置的 worker 假装走 testnet，实际 monetize 路径并没有 testnet 语义）
        trading_mode = getattr(worker, "trading_mode", "paper") or "paper"
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
            from strategy.rust_adapter import _normalize_symbol

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

            # R2 防护：特征类策略在 paper/live 无数据源，启动即拒绝（覆盖下方全部路由分支）
            self._reject_feature_strategy_if_configured(worker_id, params)

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

            # 规则/LLM 路由模式与 RL 同构：trading_config 可覆盖 worker 属性；
            # 主网闸门未开放前 live 拒绝启动（上方 RL 分支同款语义）
            rule_mode = trading_config.get("trading_mode", trading_mode)
            if rule_mode == "live":
                msg = f"worker {worker_id} 配置了主网实盘（live），主网闸门尚未开放，请先使用 testnet 模式"
                raise ValueError(msg)

            # 通过策略加载器加载策略（唯一路径：load_strategy → BaseStrategy）
            # paper/live 的 LLM 策略在这里被包成 RecordingProvider（回测则由
            # engine_service 传 run_mode="backtest" 走 replay）；testnet 实质是
            # 真实连接的实盘（合约测试网），run_mode 标 live
            strategy_instance = StrategyLoaderService.load_strategy(
                # Strategy 模型的策略名字段是 name（无 strategy_name 属性）
                strategy_name=strategy.name,
                strategy_params=params,
                instrument_ids=symbols,
                bar_types=[timeframe],
                run_mode="live" if rule_mode == "testnet" else "paper",
            )
        except Exception as e:
            logger.error(f"[StrategyManager] 策略加载失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}")
            # 加载失败直接抛出，由 start_strategy 的异常处理统一上报 worker error 状态
            raise

        logger.info(
            f"[StrategyManager] 策略已加载: worker_id={worker_id}, strategy_class={type(strategy_instance).__name__}"
        )

        # 规则/LLM 路由：testnet → LiveDriver 接合约测试网真实账户，其余按 paper 演练
        if rule_mode == "testnet":
            self.start_crypto_live(
                worker_id,
                params,
                strategy_instance,
                timeframe,
                symbols,
                exchange,
                trading_config.get("market_type", "spot"),
            )
            await self._finalize_start(worker_id, runtime, db)
            logger.info(f"[StrategyManager] 规则/LLM 实盘循环已启动: worker_id={worker_id}")
            return True

        # 规则/LLM paper 演练统一挂 PaperDriver（testnet 公共行情 + 内置撮合，
        # 与回测 Kernel 同一份 Rust 引擎口径）
        driver, risk_enabled = self._assemble_rule_paper_driver(
            worker_id, strategy_instance, params, timeframe, symbols
        )

        symbols_norm = [_normalize_symbol(s) for s in symbols]
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._paper_thread_main,
            # 首轮拉 2 根：规则/LLM 无观测窗口预热需求（RL 传 window+2）
            args=(worker_id, driver, timeframe, symbols_norm, 2, stop_event, risk_enabled),
            daemon=True,
            name=f"paper-driver-{worker_id}",
        )
        thread.start()
        self._kernel_runs[worker_id] = {"driver": driver, "stop_event": stop_event, "thread": thread}

        logger.info(
            f"[StrategyManager] paper driver 已装配: worker_id={worker_id}, "
            f"symbols={symbols_norm}, interval={timeframe}"
        )

        # 统一收尾：注册表 / DB / worker_state 三处状态流转
        await self._finalize_start(worker_id, runtime, db)

        logger.info(f"[StrategyManager] 策略已启动: worker_id={worker_id}")
        return True

    def _assemble_rule_paper_driver(
        self,
        worker_id: int,
        strategy_instance: Any,
        params: dict[str, Any],
        timeframe: str,
        symbols: list[str],
    ) -> tuple[Any, bool]:
        """装配规则/LLM 策略的 PaperDriver（不启动泵线程，可独立测试）。

        fee_rate 用引擎默认（None → 0.001），与回测 Kernel 同口径；RL 路径
        才传训练环境费率（RL_TRANSACTION_COST）。策略必须经 RustStrategyAdapter
        适配后挂载：target_position 占比换算 / hold 保持目标位 / ctx.features
        注入三处语义都由它对齐回测行为，直接挂 BaseStrategy 会全部偏差。

        Returns:
            (driver, 是否已装配 pre-trade 风控)
        """
        from axon_quant import worker as axon_worker

        from strategy.rust_adapter import RustStrategyAdapter, _normalize_symbol

        if timeframe not in _PAPER_INTERVAL_SECONDS:
            msg = f"worker {worker_id} paper 模式不支持时间周期 {timeframe}，支持: {sorted(_PAPER_INTERVAL_SECONDS)}"
            raise ValueError(msg)

        initial_cash = float(params.get("initial_capital", 100_000.0))
        symbols_norm = [_normalize_symbol(s) for s in symbols]
        driver = axon_worker.PaperDriver(symbols_norm, initial_cash=initial_cash, interval=timeframe)
        driver.add_strategy(
            # ponytail: 多品种沿用 RL 语义只挂首个品种；升级路径是每品种独立内核
            # 共享同一份决策，与回测一致
            RustStrategyAdapter(strategy_instance, initial_cash=initial_cash, symbol=symbols[0]),
            symbol=symbols_norm[0],
        )
        # B3：pre-trade 风控装配（opt-in，未配置行为不变）
        risk_enabled = apply_risk_config(driver, params, worker_id, initial_cash)
        return driver, risk_enabled

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
            params: 策略参数，需含 `model_path`；可选 `credentials_account`
                （缺省回退系统配置的测试网 Key）/ `spec_version` / `initial_capital`
            timeframe: K 线周期（驱动 bar 闭合节奏）
            symbols: 交易品种列表，RL host 只挂第一个
            exchange: 交易所标识（v1 仅 binance）
            market_type: 市场类型（v1 仅 swap/futures）

        Returns:
            运行态 dict：{driver, stop_event, thread, journal_path}
        """
        from axon_quant import worker as axon_worker
        from axon_quant.exchange import ExchangeConfig, ExchangeId

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

        # 凭证解析：策略参数 credentials_account 优先，缺省回退系统配置的测试网 Key
        api_key, api_secret = _resolve_live_credentials(worker_id, exchange, params)

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
            # adopt 持仓接管（与引擎默认一致）：fresh start 遇交易所残留持仓时
            # 抄进影子账本带仓起跑；前端本期无此表单，需要 reject 时手改 worker params
            existing_positions=params.get("existing_positions", "adopt"),
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
        # B3：pre-trade 风控装配（opt-in，未配置行为不变）
        risk_enabled = apply_risk_config(driver, params, worker_id, float(params.get("initial_capital", 100_000.0)))

        journal_path = self._rl_live_journal_path(worker_id)
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._driver_live_thread_main,
            args=(
                worker_id,
                driver,
                journal_path,
                stop_event,
                # live 成交落库：构造失败返回 None，线程内跳过轮询，不阻断启动
                self._build_live_trade_sync(worker_id, api_key, api_secret, symbols),
                risk_enabled,
            ),
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
        self._kernel_runs[worker_id] = live

        logger.info(
            f"[StrategyManager] RL LiveDriver 已装配: worker_id={worker_id}, "
            f"symbols={symbols}, interval={timeframe}, journal={journal_path}"
        )
        return live

    def start_crypto_live(
        self,
        worker_id: int,
        params: dict[str, Any],
        strategy_instance: Any,
        timeframe: str,
        symbols: list[str],
        exchange: str,
        market_type: str,
    ) -> dict[str, Any]:
        """装配规则/LLM 策略的实盘 LiveDriver 并启动逐 tick 驱动线程（testnet）。

        闸门 / 凭证 / ExchangeConfig / journal resume 语义与 start_rl_live 同构；
        差异仅在策略挂载（RustStrategyAdapter 包装 + add_strategy）与费率口径
        （引擎默认 0.001，与 paper/回测一致，不传训练环境费率）。构造过程不
        联网（connect 在驱动线程里做），配置 / 凭证问题直接抛 ValueError，
        由调用方按启动失败上报。

        v1 边界：仅 Binance USDT-M 永续 testnet（spot 不支持、主网闸门未开，
        见设计文档 9.4）。

        Args:
            worker_id: Worker ID（用于运行态缓存与 journal 定位）
            params: 策略参数；可选 `credentials_account`（缺省回退系统配置的测试网 Key）
                与 `initial_capital`
            strategy_instance: 已加载的 BaseStrategy，经 RustStrategyAdapter 包装挂载
            timeframe: K 线周期（驱动 bar 闭合节奏）
            symbols: 交易品种列表，只挂第一个
            exchange: 交易所标识（v1 仅 binance）
            market_type: 市场类型（v1 仅 swap/futures）

        Returns:
            运行态 dict：{driver, stop_event, thread, journal_path}
        """
        from axon_quant import worker as axon_worker
        from axon_quant.exchange import ExchangeConfig, ExchangeId

        from strategy.rust_adapter import RustStrategyAdapter, _normalize_symbol

        if exchange.lower() != "binance":
            msg = f"worker {worker_id} 实盘暂只支持 binance，当前配置: {exchange}"
            raise ValueError(msg)
        if market_type not in ("swap", "futures"):
            msg = (
                f"worker {worker_id} 实盘 v1 仅支持永续合约（swap/futures），"
                f"当前 market_type={market_type}，spot 暂不支持"
            )
            raise ValueError(msg)

        # 凭证解析：策略参数 credentials_account 优先，缺省回退系统配置的测试网 Key
        api_key, api_secret = _resolve_live_credentials(worker_id, exchange, params)

        # 与 start_rl_live 相同：binance_testnet_config() 是现货 URL，这里手工
        # 构造 USDT-M 合约测试网配置（URL 与 exchange/binance/exchange.py 一致）
        config = ExchangeConfig(
            exchange_id=ExchangeId.Binance,
            api_key=api_key,
            api_secret=api_secret,
            rest_base_url="https://testnet.binancefuture.com",
            ws_url="wss://stream.binancefuture.com/ws",
            testnet=True,
        )

        initial_cash = float(params.get("initial_capital", 100_000.0))
        driver = axon_worker.LiveDriver(
            config,
            [_normalize_symbol(s) for s in symbols],
            initial_cash=initial_cash,
            interval=timeframe,
            # adopt 持仓接管（与引擎默认一致）：fresh start 遇交易所残留持仓时
            # 抄进影子账本带仓起跑；前端本期无此表单，需要 reject 时手改 worker params
            existing_positions=params.get("existing_positions", "adopt"),
        )
        driver.add_strategy(
            # ponytail: 多品种沿用 RL/paper 语义只挂首个品种；升级路径是每品种
            # 独立内核共享同一份决策，与回测一致
            RustStrategyAdapter(strategy_instance, initial_cash=initial_cash, symbol=symbols[0]),
            symbol=_normalize_symbol(symbols[0]),
        )
        # B3：pre-trade 风控装配（opt-in，未配置行为不变）
        risk_enabled = apply_risk_config(driver, params, worker_id, initial_cash)

        journal_path = self._live_journal_path(worker_id)
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._driver_live_thread_main,
            args=(
                worker_id,
                driver,
                journal_path,
                stop_event,
                # live 成交落库：构造失败返回 None，线程内跳过轮询，不阻断启动
                self._build_live_trade_sync(worker_id, api_key, api_secret, symbols),
                risk_enabled,
            ),
            daemon=True,
            name=f"live-{worker_id}",
        )
        thread.start()
        live = {"driver": driver, "stop_event": stop_event, "thread": thread, "journal_path": journal_path}
        self._kernel_runs[worker_id] = live

        logger.info(
            f"[StrategyManager] LiveDriver 已装配（规则/LLM）: worker_id={worker_id}, "
            f"symbols={symbols}, interval={timeframe}, journal={journal_path}"
        )
        return live

    @staticmethod
    def _reject_feature_strategy_if_configured(worker_id: int, params: dict[str, Any]) -> None:
        """R2 防护：配置了因子特征的策略拒绝 paper/testnet（live）启动。

        回测由 engine_service 按 factor_name/factor_names attach_feature_frames
        逐 bar 注入 ctx.features；paper/live 只喂 OHLCV bar（PaperDriver/LiveDriver
        无特征帧通道），ctx.has_feature 恒 False —— 引擎按 hold 静默空转而非报错，
        与回测行为不一致。在装备期显式拒绝，避免用户拿着空转的 paper 当验证结论。
        """
        factor_name = str(params.get("factor_name") or "").strip()
        factor_names = params.get("factor_names")
        if factor_name or factor_names:
            msg = (
                f"worker {worker_id} 配置了因子特征参数（factor_name/factor_names）。"
                "paper/testnet 实练不注入逐 bar 因子特征，策略将全程 hold 空转；"
                "特征类策略仅支持回测验证，请去掉该参数或改用回测"
            )
            raise ValueError(msg)

    @staticmethod
    def _build_live_trade_sync(worker_id: int, api_key: str, api_secret: str, symbols: list[str]) -> Any | None:
        """构造 live 成交落库同步器（B2：live 成交不落 DB 的修复）。

        复用 start_*_live 已取得的凭证；symbol 归一化与 LiveDriver 同源。
        构造失败只记日志并返回 None（观测性组件，不阻断实盘启动）。
        """
        # 与 start_*_live 一致的函数内 import：rust_adapter 依赖 axon_quant，
        # 延迟到调用时加载，避免加重模块链
        from strategy.rust_adapter import _normalize_symbol

        try:
            return LiveTradeSync(
                worker_id=worker_id,
                api_key=api_key,
                api_secret=api_secret,
                symbol=_normalize_symbol(symbols[0]),
            )
        except Exception as e:
            logger.warning(
                f"[StrategyManager] LiveTradeSync 构造失败，live 成交将不落库: worker_id={worker_id}, error={e}"
            )
            return None

    def _driver_live_thread_main(
        self,
        worker_id: int,
        driver: Any,
        journal_path: str,
        stop_event: threading.Event,
        trade_sync: Any | None = None,
        risk_enabled: bool = False,
    ) -> None:
        """实盘驱动线程（RL / 规则 / LLM LiveDriver 共用）：connect → resume/start → 1s 轮询 tick。

        线程内没有调用方可接异常，连接失败统一降级为 worker error 状态
        （registry + DB），线程自身退出；单次 tick 异常只记日志继续。
        trade_sync 非空时按窗口节流轮询交易所成交并落库，失败只记日志。
        risk_enabled 时按 DB 当日已实现盈亏回灌风控（每轮检查跨日清零）。
        """
        # per-worker 日志通道：sink 挂载失败/线程早退时不卸载，错误日志仍能被前端看到
        start_worker_log_sink(worker_id)
        # 线程内日志统一 bind worker_id，经 log_utils 的 per-worker sink 分流到
        # logs/worker/worker_{id}.log + 内存环，供前端日志面板读取
        wlog = logger.bind(worker_id=worker_id)
        journal = Path(journal_path)
        try:
            driver.connect()
            if journal.is_file() and journal.stat().st_size > 0:
                # 崩溃恢复：重演 journal + 对账，报告仅记日志
                report = driver.resume(str(journal))
                wlog.info(f"[StrategyManager] 实盘恢复完成: worker_id={worker_id}, report={report}")
            else:
                driver.start(str(journal))
        except Exception as e:
            wlog.error(
                f"[StrategyManager] 实盘连接/恢复失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            self._mark_rl_live_error(worker_id, f"实盘连接/恢复失败: {e}")
            # 线程已死，原地清掉运行态，避免残留条目让后续 stop/restart 摸到僵尸驱动
            self._kernel_runs.pop(worker_id, None)
            return

        wlog.info(f"[StrategyManager] 实盘 tick 循环启动: worker_id={worker_id}")
        last_snapshot = float("-inf")
        last_trade_sync = 0.0
        # 当日盈亏回灌：live 以 DB 当日已实现盈亏为准（重启不重置当日亏损额度）。
        # 注意 resume 恢复路径不装配风控（Rust 侧契约），此时绑定层方法 no-op
        pnl_feeder = RiskPnlFeeder(driver, daily_scoped=True) if risk_enabled else None
        if pnl_feeder is not None and trade_sync is not None:
            try:
                pnl_feeder.feed(trade_sync.daily_realized_pnl())
            except Exception as e:
                wlog.warning(f"[StrategyManager] live 当日盈亏首次回灌失败: worker_id={worker_id}, error={e}")
        # 风控拒单（Rust 侧 "risk rejected: {reason}"）是设计内行为（拒开仓放减仓），
        # live 1s/tick 会持续命中同一原因，按原因去重防刷屏；tick 恢复后清空再触发才重记
        last_risk_reject: str | None = None
        while not stop_event.is_set():
            # 跨日清零必须每轮做：昨日熔断若只在成交时解除，空仓账户会永远等不到
            if pnl_feeder is not None:
                try:
                    pnl_feeder.reset_if_new_day()
                except Exception as e:
                    wlog.warning(f"[StrategyManager] live 风控跨日清零失败: worker_id={worker_id}, error={e}")
            try:
                driver.tick()
                last_risk_reject = None
            except Exception as e:
                msg = str(e)
                if msg.startswith("risk rejected: "):
                    reason = msg.removeprefix("risk rejected: ")
                    if reason != last_risk_reject:
                        last_risk_reject = reason
                        wlog.warning(
                            f"[StrategyManager] 风控拒单(拒开仓放减仓): worker_id={worker_id}, reason={reason}"
                        )
                else:
                    last_risk_reject = None
                    wlog.error(f"[StrategyManager] 实盘 tick 异常: worker_id={worker_id}, error={e}")
            # snapshot 推送按窗口节流，失败静默（观测性推送不反噬交易循环）
            now_s = time.monotonic()
            if now_s - last_snapshot >= _LIVE_SNAPSHOT_INTERVAL_S:
                last_snapshot = now_s
                try:
                    self._push_kernel_snapshot(worker_id, driver.snapshot())
                except Exception as e:
                    wlog.debug(f"[StrategyManager] live snapshot 推送失败: worker_id={worker_id}, error={e}")
            # live 成交落库轮询按窗口节流，失败只记日志（同 snapshot：观测性不反噬交易循环）
            if trade_sync is not None and now_s - last_trade_sync >= LIVE_TRADE_SYNC_INTERVAL_S:
                last_trade_sync = now_s
                try:
                    inserted = trade_sync.sync_once()
                except Exception as e:
                    inserted = 0
                    wlog.warning(f"[StrategyManager] live 成交落库轮询失败: worker_id={worker_id}, error={e}")
                # 有新成交才查当日汇总：回灌是风控额度更新，不能靠旧值漂移
                if inserted and pnl_feeder is not None:
                    try:
                        pnl_feeder.feed(trade_sync.daily_realized_pnl())
                    except Exception as e:
                        wlog.warning(f"[StrategyManager] live 当日盈亏回灌失败: worker_id={worker_id}, error={e}")
            # wait 而非 sleep：stop 可即时唤醒
            stop_event.wait(_LIVE_TICK_INTERVAL_S)

        wlog.info(f"[StrategyManager] 实盘 tick 循环退出: worker_id={worker_id}")

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
        if timeframe not in _PAPER_INTERVAL_SECONDS:
            msg = f"worker {worker_id} RL paper 不支持时间周期 {timeframe}，支持: {sorted(_PAPER_INTERVAL_SECONDS)}"
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
        # B3：pre-trade 风控装配（opt-in，未配置行为不变）
        risk_enabled = apply_risk_config(driver, params, worker_id, float(params.get("initial_capital", 100_000.0)))

        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._paper_thread_main,
            args=(
                worker_id,
                driver,
                timeframe,
                [_normalize_symbol(s) for s in symbols],
                # 首轮拉取条数：补满 RL 观测窗口再留 2 根余量，由通用泵原样使用
                spec["window_size"] + 2,
                stop_event,
                risk_enabled,
            ),
            daemon=True,
            name=f"rl-paper-{worker_id}",
        )
        thread.start()
        paper = {"driver": driver, "stop_event": stop_event, "thread": thread}
        self._kernel_runs[worker_id] = paper

        logger.info(
            f"[StrategyManager] RL PaperDriver 已装配: worker_id={worker_id}, symbols={symbols}, interval={timeframe}"
        )
        return paper

    def _paper_thread_main(
        self,
        worker_id: int,
        driver: Any,
        timeframe: str,
        symbols: list[str],
        first_limit: int,
        stop_event: threading.Event,
        risk_enabled: bool = False,
    ) -> None:
        """paper 行情泵驱动线程（RL/规则/LLM driver 共用）：start → 睡到收市点 → 拉收市 K 线喂 driver。

        与 live 驱动线程一样线程内自兜底：启动失败降级 worker error，
        单轮拉取/喂单异常只记日志继续。停机的 driver.shutdown 由 stop_strategy
        统一做（线程退出后才能安全 shutdown）。

        Args:
            first_limit: 首轮拉取的 K 线条数（调用方按需决定，如 RL 传观测窗口+2）；
                之后固定拉最近 2 根防窗口重叠
            risk_enabled: 是否已装配 pre-trade 风控（决定是否启用当日盈亏回灌）
        """
        # per-worker 日志通道：sink 挂载失败/线程早退时不卸载，错误日志仍能被前端看到
        start_worker_log_sink(worker_id)
        # 线程内日志统一 bind worker_id，经 log_utils 的 per-worker sink 分流到
        # logs/worker/worker_{id}.log + 内存环，供前端日志面板读取
        wlog = logger.bind(worker_id=worker_id)
        step_s = _PAPER_INTERVAL_SECONDS.get(timeframe, 60)
        try:
            driver.start()
        except Exception as e:
            wlog.error(
                f"[StrategyManager] paper 泵启动失败: worker_id={worker_id}, error={e}\n{traceback.format_exc()}"
            )
            self._mark_rl_live_error(worker_id, f"paper 泵启动失败: {e}")
            return

        wlog.info(f"[StrategyManager] paper 泵循环启动: worker_id={worker_id}, interval={timeframe}")
        limit = first_limit
        seen_open_ms: dict[str, int] = {}
        # 当日盈亏回灌：paper 账纯内存，用权益差值（含盯市）换算当日盈亏
        pnl_feeder = RiskPnlFeeder(driver, daily_scoped=False) if risk_enabled else None
        # 风控拒单（Rust 侧 "risk rejected: {reason}"）是设计内行为（拒开仓放减仓），
        # 按原因去重防逐 bar 刷屏；泵轮恢复后清空再触发才重记（同 live 泵）
        last_risk_reject: str | None = None
        # 成交落库：内核 fill 只存 Rust 内存，泵轮后增量拉取落库（失败只记日志）
        trade_sync = PaperTradeSync(worker_id)
        while not stop_event.is_set():
            try:
                self._paper_pump_round(worker_id, driver, symbols, timeframe, seen_open_ms, limit, pnl_feeder, wlog)
                limit = 2
                last_risk_reject = None
            except Exception as e:
                msg = str(e)
                if msg.startswith("risk rejected: "):
                    reason = msg.removeprefix("risk rejected: ")
                    if reason != last_risk_reject:
                        last_risk_reject = reason
                        wlog.warning(
                            f"[StrategyManager] 风控拒单(拒开仓放减仓): worker_id={worker_id}, reason={reason}"
                        )
                else:
                    last_risk_reject = None
                    wlog.error(f"[StrategyManager] paper 泵拉取/喂单异常: worker_id={worker_id}, error={e}")
                # ponytail: 连续失败跨多根 K 线会漏 bar（下轮 limit=2 补不回更早的），
                # paper 演练可接受；彻底解法按 seen 与当前时间差值动态拉取
            try:
                trade_sync.sync_once(driver)
            except Exception as e:
                wlog.warning(f"[StrategyManager] paper 成交落库失败: worker_id={worker_id}, error={e}")
            # wait 而非 sleep：stop 可即时唤醒；+0.5s 缓冲等交易所端收市 K 线就绪
            stop_event.wait(step_s - (time.time() % step_s) + 0.5)

        wlog.info(f"[StrategyManager] paper 泵循环退出: worker_id={worker_id}")

    def _paper_pump_round(
        self,
        worker_id: int,
        driver: Any,
        symbols: list[str],
        timeframe: str,
        seen_open_ms: dict[str, int],
        limit: int,
        pnl_feeder: RiskPnlFeeder | None = None,
        wlog: Any | None = None,
    ) -> None:
        """拉一轮收市 K 线并注入 driver，全部喂完后 tick 一次。

        已收市判定用 open_ms + step_ms <= now（不信任交易所 closeTime 的 -1ms
        惯例）；按开市时间去重，REST 窗口重叠时不会重复喂同一根 bar。
        抽成独立方法：线程循环只负责节拍，这份核心逻辑可在测试中同步直调。

        Args:
            pnl_feeder: 非空时用权益快照回灌当日盈亏（B3 风控，跨日清零由其内部处理）
            wlog: 泵线程绑定的 worker 日志句柄；测试同步直调时可缺省，回退全局 logger
        """
        log = wlog or logger
        step_ms = _PAPER_INTERVAL_SECONDS[timeframe] * 1000
        now_ms = int(time.time() * 1000)
        for symbol in symbols:
            api_symbol = symbol.replace("/", "")  # BTC/USDT → BTCUSDT
            for row in self._paper_fetch_klines(api_symbol, timeframe, limit):
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
        # 泵轮末尾只取一次快照：当日盈亏回灌与前端推送共用
        try:
            snap = driver.snapshot()
        except Exception as e:
            log.debug(f"[StrategyManager] paper snapshot 获取失败: worker_id={worker_id}, error={e}")
            return
        if pnl_feeder is not None:
            try:
                pnl_feeder.feed(float(snap.get("equity") or 0.0))
            except Exception as e:
                # 回灌失败只降级告警：风控额度暂时失真，但不能停掉行情泵
                log.warning(f"[StrategyManager] paper 当日盈亏回灌失败: worker_id={worker_id}, error={e}")
        # 观测性推送，失败不打断行情泵
        try:
            self._push_kernel_snapshot(worker_id, snap)
        except Exception as e:
            log.debug(f"[StrategyManager] paper snapshot 推送失败: worker_id={worker_id}, error={e}")

    def _paper_fetch_klines(self, api_symbol: str, timeframe: str, limit: int) -> list[list]:
        """拉 binance USDT-M testnet 公共收市 K 线（不签名）。

        ponytail: 标准库 urlopen 就够（一次 GET + timeout）；requests 未在
        pyproject 声明为直接依赖（只是 python-binance 的传递依赖），不为一次
        调用把它升级成直接依赖。symbol/timeframe 均来自白名单受限字符集，
        URL 无需额外编码。

        Returns:
            binance 原始行：[openTime, open, high, low, close, volume, ...]（数值是字符串）
        """
        url = f"{_PAPER_KLINES_URL}?symbol={api_symbol}&interval={timeframe}&limit={limit}"
        with _PAPER_NO_PROXY_OPENER.open(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _push_kernel_snapshot(worker_id: int, snap: Any) -> None:
        """把 driver.snapshot() 转成 kernel.snapshot 事件推到前端 WS 通道。

        形状 {"event": "kernel.snapshot", worker_id, equity, positions}；主 loop
        未就绪时 broadcast_threadsafe 静默丢弃，这里只做形状转换。
        """
        if not isinstance(snap, dict):
            return
        from .state import connection_manager

        connection_manager.broadcast_threadsafe(
            {
                "event": "kernel.snapshot",
                "worker_id": worker_id,
                "equity": snap.get("equity"),
                "positions": snap.get("positions"),
            }
        )

    def _mark_rl_live_error(self, worker_id: int, message: str) -> None:
        """把驱动循环（RL live/paper、规则/LLM live、paper 泵）运行失败落到 registry + DB 的 error 状态。

        线程内的失败没有启动调用方兜底，必须自带上报；DB 写失败不影响降级结果。
        """
        from .state import strategy_registry

        strategy_registry.update_status(worker_id, "error", error_message=message)
        # 驱动循环的失败可能发生在 sink 挂载之外（如 RL 推理循环），同样手动双写
        append_worker_error_log(worker_id, f"运行失败: {message}")
        # 第三层：worker_state_manager 缓存 + WS 广播 + DB 持久化（transition 是 async，
        # 泵线程没有运行中的事件循环，用 asyncio.run 短暂桥接；transition 返回 bool、
        # 失败不抛异常。此层失败仅记日志，不影响上面两层落账）
        try:
            transitioned = asyncio.run(worker_state_manager.transition(worker_id, "error", error_message=message))
            if not transitioned:
                logger.warning(
                    f"[StrategyManager] 第三层状态转换未生效（非法转换或 worker 不存在）: "
                    f"worker_id={worker_id}, error={message}"
                )
        except Exception as e:
            logger.error(f"[StrategyManager] 第三层状态同步失败: worker_id={worker_id}, error={e}")
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

    def _live_journal_path(self, worker_id: int) -> str:
        """规则/LLM 实盘 journal 文件路径：backend/data/live/worker_{id}.jsonl。

        与 RL 的 data/rl_live/ 分目录：存量 RL journal 的 resume 指纹不因本路径引入变化。
        """
        data_dir = os.environ.get("QUANTCELL_DATA_DIR")
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "data"
        live_dir = base / "live"
        live_dir.mkdir(parents=True, exist_ok=True)
        return str(live_dir / f"worker_{worker_id}.jsonl")

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

        # driver 运行态（规则/LLM paper、RL paper、RL live 共用）：先通知停驱动线程
        # 并等待退出，再收口 driver（线程退出前 driver 仍被循环使用，必须先 join）
        run = self._kernel_runs.pop(worker_id, None)
        if run is not None:
            run["stop_event"].set()
            run["thread"].join(timeout=5)
            if run["thread"].is_alive():
                logger.error(f"[StrategyManager] driver 线程未能在 5s 内停止: worker_id={worker_id}")
            try:
                run["driver"].shutdown()
            except Exception as e:
                logger.error(f"[StrategyManager] driver 关闭失败: worker_id={worker_id}, error={e}")

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

        # 先经 per-worker 通道通告停止（前端日志面板），再卸 sink；此后不再有该 worker 的运行期日志
        logger.bind(worker_id=worker_id).info(f"[StrategyManager] 策略已停止: worker_id={worker_id}")
        stop_worker_log_sink(worker_id)
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
        # stop 路径已卸则幂等静默；stopped 状态直达删除（不经 stop）时兜底清理
        stop_worker_log_sink(worker_id)
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
        running = [s for s in strategies if s.status == "running"]
        # mode 按运行中策略的实际 trading_mode 推导（此前恒报 paper 是假数据）；
        # 无运行中策略时为 None，多种 mode 并存时报 mixed
        modes = {s.mode for s in running}
        if not modes:
            mode: str | None = None
        elif len(modes) == 1:
            mode = modes.pop()
        else:
            mode = "mixed"
        return {
            "exchange": "binance",
            "mode": mode,
            # B3 起 pre-trade 风控已接线到 paper/live 驱动（axon-risk 引擎），
            # 是否对某个 worker 生效由 params.risk / worker_risk_control 决定（opt-in）
            "risk_available": True,
            "total_strategies": len(strategies),
            "running_strategies": len(running),
        }

    def get_running_driver(self, worker_id: int) -> Any | None:
        """返回 worker 当前运行的 driver（paper/live 泵）——人工风控实时推送目标；未运行返回 None。

        stop 各路径已 pop _kernel_runs 并对 driver shutdown，无需在此额外处理。
        """
        run = self._kernel_runs.get(worker_id)
        return run.get("driver") if run else None

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

        # 停掉 driver 驱动线程并收口（规则/LLM paper、RL paper、RL live 共用）
        for worker_id, run in self._kernel_runs.items():
            try:
                run["stop_event"].set()
                run["thread"].join(timeout=5)
                if run["thread"].is_alive():
                    logger.warning(f"[StrategyManager] shutdown: worker_id={worker_id} driver线程未在 5s 内停止")
                run["driver"].shutdown()
                logger.info(f"[StrategyManager] shutdown: worker_id={worker_id} driver 已停止")
            except Exception as e:
                logger.warning(f"[StrategyManager] shutdown: worker_id={worker_id} 停止 driver 失败: {e}")
        self._kernel_runs.clear()

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
