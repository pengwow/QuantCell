"""
Worker 进程实现

在独立进程中运行策略，通过进程间通信与主进程交互
"""

import multiprocessing
import asyncio
import signal
import os
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime
import json
from utils.logger import get_logger, LogType
from core.port_manager import port_manager

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from .ipc import WorkerCommClient, Message, MessageType
from .state import WorkerState, WorkerStatus
from .unified_file_logger import create_unified_logger


class WorkerProcess(multiprocessing.Process):
    """
    策略工作进程

    在完全隔离的 Python 进程中运行单个策略，
    通过进程间通信与主进程进行交互
    """

    def __init__(
        self,
        worker_id: str,
        strategy_path: str,
        config: Dict[str, Any],
        comm_host: str = "127.0.0.1",
        data_port: Optional[int] = None,
        control_port: Optional[int] = None,
        status_port: Optional[int] = None,
    ):
        super().__init__(daemon=True)

        self.worker_id = worker_id
        self.strategy_path = strategy_path
        self.config = config
        self.comm_host = comm_host
        # 从 PortManager 获取端口（如果未提供）
        self.data_port = data_port if data_port is not None else port_manager.get_port("zmq_data")
        self.control_port = control_port if control_port is not None else port_manager.get_port("zmq_control")
        self.status_port = status_port if status_port is not None else port_manager.get_port("zmq_status")

        logger.info(f"初始化 Worker 进程 | worker_id={worker_id} | data_port={self.data_port} | control_port={self.control_port} | status_port={self.status_port}")

        # 进程内状态
        self.status = WorkerStatus(
            worker_id=worker_id,
            strategy_path=strategy_path,
            symbols=config.get("symbols", []),
        )
        self.comm_client: Optional[WorkerCommClient] = None
        self.strategy: Optional[Any] = None

        # 运行控制
        self._shutdown_event = multiprocessing.Event()

        # 标记是否需要优雅停止（用于区分信号停止和控制消息停止）
        self._graceful_stop_requested = False

        # 统计信息
        self._messages_processed = 0
        self._orders_placed = 0

        # 交易记录缓存（用于采集 NautilusTrader 的成交数据）
        self._trade_records: List[Dict[str, Any]] = []
        self._max_trade_records: int = 1000
        self._last_save_time: float = 0.0

    def run(self):
        """
        进程主入口

        这是进程启动时调用的方法，设置进程环境并启动主循环
        """
        # 设置环境变量，标识这是 Worker 进程
        os.environ['WORKER_ID'] = str(self.worker_id)

        # 初始化统一文件日志器（确保所有日志都写入 worker_{id}.log）
        try:
            unified_file_logger = create_unified_logger(
                worker_id=str(self.worker_id),
                log_directory="logs",
            )
            # 安装各种日志捕获器
            unified_file_logger.install_stdout_capture()    # 捕获 stdout 输出
            unified_file_logger.install_stderr_capture()    # 捕获 stderr 输出（NautilusTrader 警告/错误日志）
            unified_file_logger.install_logging_handler()   # 捕获 logging 模块日志
            unified_file_logger.install_loguru_sink()       # 捕获 loguru 日志（DEBUG 及以上级别）
            logger.info(f"[WorkerProcess] 统一文件日志器已初始化: logs/worker_{self.worker_id}.log")
        except Exception as e:
            logger.error(f"[WorkerProcess] 初始化统一文件日志器失败: {e}", exc_info=True)

        # 调试：记录子进程中的 worker_id
        logger.info(f"[WorkerProcess.run] 子进程启动，worker_id={self.worker_id}, pid={os.getpid()}")

        # 设置进程标题
        try:
            import setproctitle
            setproctitle.setproctitle(f"quantcell-worker:{self.worker_id}")
        except ImportError:
            pass

        # 设置进程 ID
        self.status.pid = os.getpid()

        # 设置信号处理
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._main_loop())
        except asyncio.CancelledError:
            logger.info(f"Worker {self.worker_id} 收到取消信号，正在优雅退出")
        except Exception as e:
            logger.error(f"Worker {self.worker_id} 主循环异常: {e}")
            self.status.record_error(str(e))
        finally:
            # 清理所有未完成的 pending tasks（避免 "Task was destroyed but it is pending" 警告）
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.debug(f"Worker {self.worker_id} 正在清理 {len(pending)} 个 pending tasks...")
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as e:
                logger.warning(f"Worker {self.worker_id} 清理 pending tasks 时出错: {e}")

            loop.run_until_complete(self._cleanup())
            loop.close()

    async def _main_loop(self):
        """
        主事件循环

        初始化并运行 Worker 的主要逻辑
        """
        try:
            logger.info(f"[_main_loop] Worker {self.worker_id} 开始执行 _main_loop")

            # 1. 初始化通信连接
            logger.info(f"[_main_loop] Worker {self.worker_id} 开始 _init_comm")
            await self._init_comm()
            logger.info(f"[_main_loop] Worker {self.worker_id} _init_comm 完成")

            # 2. 加载策略（在进程内部加载，确保隔离）
            logger.info(f"[_main_loop] Worker {self.worker_id} 开始 _load_strategy")
            await self._load_strategy()
            logger.info(f"[_main_loop] Worker {self.worker_id} _load_strategy 完成")

            # 3. 订阅数据
            logger.info(f"[_main_loop] Worker {self.worker_id} 开始 _subscribe_data")
            await self._subscribe_data()
            logger.info(f"[_main_loop] Worker {self.worker_id} _subscribe_data 完成")

            # 4. 启动完成，发送状态更新
            # 状态流转: INITIALIZED -> STARTING -> RUNNING
            logger.info(f"[_main_loop] Worker {self.worker_id} 准备更新状态为 STARTING")
            self.status.update_state(WorkerState.STARTING)
            logger.info(f"[_main_loop] Worker {self.worker_id} 状态已更新为 STARTING")

            logger.info(f"[_main_loop] Worker {self.worker_id} 准备更新状态为 RUNNING")
            self.status.update_state(WorkerState.RUNNING)
            logger.info(f"[_main_loop] Worker {self.worker_id} 状态已更新为 RUNNING，准备发送状态消息")
            send_result = await self._send_status(MessageType.STATUS_UPDATE)
            logger.info(f"[_main_loop] Worker {self.worker_id} 状态消息发送结果: {send_result}")

            logger.info(f"[_main_loop] Worker {self.worker_id} 启动完成，开始运行")

            # 5. 主循环 - 等待关闭信号
            logger.info(f"[WorkerProcess] Worker {self.worker_id} 进入主循环，等待 _shutdown_event...")
            while not self._shutdown_event.is_set():
                # 发送心跳
                await self._send_heartbeat()

                # 等待一段时间
                await asyncio.sleep(5)

            logger.info(f"[WorkerProcess] Worker {self.worker_id} 主循环退出，_shutdown_event 已设置")

            # 如果是通过信号触发的停止，执行完整的优雅停止流程（停止 Nautilus）
            if self._graceful_stop_requested:
                logger.info(f"[WorkerProcess] 检测到优雅停止请求，执行 Nautilus 停止流程...")
                try:
                    await self._handle_stop()
                except Exception as e:
                    logger.error(f"[WorkerProcess] 优雅停止 Nautilus 失败: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info(f"Worker {self.worker_id} 控制循环被取消，正在优雅退出")
        except Exception as e:
            logger.error(f"[WorkerProcess] Worker {self.worker_id} 主循环异常: {e}")
            self.status.update_state(WorkerState.ERROR)
            self.status.record_error(str(e))
            await self._send_status(MessageType.ERROR)
            raise

    async def _init_comm(self):
        """
        初始化通信连接
        """
        self.comm_client = WorkerCommClient(
            worker_id=self.worker_id,
            host=self.comm_host,
            data_port=self.data_port,
            control_port=self.control_port,
            status_port=self.status_port,
        )

        # 注册消息处理器
        self.comm_client.register_data_handler(self._handle_data)
        self.comm_client.register_control_handler(self._handle_control)

        # 连接到主进程
        success = await self.comm_client.connect()
        if not success:
            raise RuntimeError("无法连接到通信服务")

        self.status.update_state(WorkerState.INITIALIZED)
        logger.info(f"Worker {self.worker_id} 通信连接已建立")

    async def _load_strategy(self):
        """
        动态加载策略

        在进程内部动态加载策略模块，确保策略代码的隔离性。
        优先从数据库加载策略代码，如果数据库中没有则从文件系统加载。
        """
        try:
            import sys
            import types

            # 优先使用从 config 传递的策略代码
            strategy_code: Optional[str] = self.config.get("strategy_code")
            strategy_name: Optional[str] = None

            if strategy_code:
                logger.info(f"Worker {self.worker_id} 使用从配置传递的策略代码")
            else:
                # 尝试从数据库加载策略代码
                try:
                    # 导入数据库相关模块
                    from collector.db.database import init_database_config, SessionLocal
                    from strategy.models import Strategy

                    # 初始化数据库配置
                    init_database_config()

                    # 从数据库获取策略代码
                    db = SessionLocal()
                    try:
                        strategy_id = self.config.get("strategy_id")
                        if strategy_id:
                            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
                            if strategy is not None:
                                code = getattr(strategy, 'code', None)
                                name = getattr(strategy, 'name', None)
                                if code:
                                    strategy_code = str(code)
                                    strategy_name = str(name) if name else None
                                    logger.info(f"Worker {self.worker_id} 从数据库加载策略: {name}")
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"从数据库加载策略失败，尝试从文件加载: {e}")

                # 如果从数据库加载失败，尝试从文件加载
                if not strategy_code:
                    if not self.strategy_path or not os.path.exists(self.strategy_path):
                        raise ImportError(f"策略文件不存在: {self.strategy_path}")

                    with open(self.strategy_path, 'r', encoding='utf-8') as f:
                        strategy_code = f.read()
                    logger.info(f"Worker {self.worker_id} 从文件加载策略: {self.strategy_path}")

            # 动态创建模块
            module_name = f"strategy_{self.worker_id}"
            module = types.ModuleType(module_name)
            sys.modules[module_name] = module

            # 执行策略代码
            if strategy_code:
                exec(strategy_code, module.__dict__)
            else:
                raise ImportError("策略代码为空")

            # 获取策略类
            strategy_class_name = self.config.get("strategy_class", "Strategy")
            logger.info(f"[_load_strategy] 尝试获取策略类: {strategy_class_name}")
            strategy_class = getattr(module, strategy_class_name, None)
            logger.info(f"[_load_strategy] getattr 结果: {strategy_class}")

            # 检查获取的类是否有效（不能是基类）
            from strategy.core import StrategyBase
            if strategy_class is not None:
                is_valid = True
                # 排除基类名称
                if strategy_class_name in ["StrategyBase", "Strategy"]:
                    is_valid = False
                    logger.info(f"[_load_strategy] 策略类名 {strategy_class_name} 是基类名称，需要重新查找")
                # 排除抽象基类
                elif isinstance(strategy_class, type):
                    try:
                        if issubclass(strategy_class, StrategyBase) and strategy_class is StrategyBase:
                            is_valid = False
                            logger.info(f"[_load_strategy] 策略类 {strategy_class_name} 是 StrategyBase 基类，需要重新查找")
                    except TypeError:
                        pass

                if not is_valid:
                    strategy_class = None

            if strategy_class is None:
                # 尝试查找策略类（优先查找继承自 StrategyBase 的类）
                import typing
                logger.info(f"[_load_strategy] 开始遍历模块查找策略类")

                # 第一轮：查找继承自 StrategyBase 的具体策略类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    is_type = isinstance(attr, type)
                    not_excluded_name = attr_name not in ["StrategyBase", "Strategy", "object"]
                    not_private = not attr_name.startswith("_")
                    not_typing = (attr is not typing.Any and
                                 attr is not typing.Dict and
                                 attr is not typing.List and
                                 attr is not typing.Optional and
                                 not hasattr(typing, attr_name))

                    # 检查是否是 StrategyBase 的子类（但不是 StrategyBase 本身）
                    is_strategy_subclass = False
                    if is_type and not_excluded_name and not_private and not_typing:
                        try:
                            is_strategy_subclass = (issubclass(attr, StrategyBase) and attr is not StrategyBase)
                        except TypeError:
                            pass

                    logger.info(f"[_load_strategy] 第一轮检查类 {attr_name}: is_type={is_type}, is_strategy_subclass={is_strategy_subclass}")

                    if is_strategy_subclass:
                        strategy_class = attr
                        logger.info(f"[_load_strategy] 第一轮找到策略类: {attr_name} -> {attr}")
                        break

                # 第二轮：如果没有找到，查找其他有效的类
                if strategy_class is None:
                    logger.info(f"[_load_strategy] 第二轮：查找其他有效的类")
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        is_type = isinstance(attr, type)
                        not_excluded_name = attr_name not in ["StrategyBase", "Strategy", "object"]
                        not_private = not attr_name.startswith("_")
                        not_typing = (attr is not typing.Any and
                                     attr is not typing.Dict and
                                     attr is not typing.List and
                                     attr is not typing.Optional and
                                     not hasattr(typing, attr_name))
                        # 排除 StrategyBase 本身
                        is_strategy_base_itself = False
                        if is_type:
                            try:
                                is_strategy_base_itself = (issubclass(attr, StrategyBase) and attr is StrategyBase)
                            except TypeError:
                                pass
                        not_strategy_base_itself = not is_strategy_base_itself

                        logger.info(f"[_load_strategy] 第二轮检查类 {attr_name}: is_type={is_type}, not_excluded_name={not_excluded_name}, not_private={not_private}, not_typing={not_typing}, not_strategy_base_itself={not_strategy_base_itself}")

                        if (is_type and
                            not_excluded_name and
                            not_private and
                            not_typing and
                            not_strategy_base_itself):
                            strategy_class = attr
                            logger.info(f"[_load_strategy] 第二轮找到策略类: {attr_name} -> {attr}")
                            break

            if strategy_class is None:
                raise ImportError(f"在策略代码中未找到策略类")

            # 实例化策略
            # 检查是否是 Nautilus 格式的策略
            is_nautilus_strategy = False

            try:
                from strategy.core import StrategyBase as QuantCellStrategyBase

                # 检查 1: QuantCell 旧基类的子类
                if issubclass(strategy_class, QuantCellStrategyBase):
                    is_nautilus_strategy = True
                    logger.info(f"[_load_strategy] 策略是 QuantCell StrategyBase 子类")
            except TypeError:
                pass  # strategy_class 不是类

            try:
                # 检查 2: NautilusTrader 原生 Strategy 的子类（Cython 编译）
                from nautilus_trader.trading.strategy import Strategy as NautilusStrategy

                if not is_nautilus_strategy and issubclass(strategy_class, NautilusStrategy):
                    is_nautilus_strategy = True
                    logger.info(f"[_load_strategy] 策略是 NautilusTrader 原生 Strategy 子类")
            except (TypeError, ImportError) as e:
                logger.debug(f"[_load_strategy] 检查 NautilusStrategy 失败: {e}")
                pass  # 导入失败或不是类

            # 检查 3: 通过属性特征判断（兜底）
            if not is_nautilus_strategy:
                nautilus_attrs = ['order_factory', 'portfolio', 'cache', 'submit_order', 'cancel_order']
                has_nautilus_attrs = all(hasattr(strategy_class, attr) for attr in nautilus_attrs)
                if has_nautilus_attrs:
                    is_nautilus_strategy = True
                    logger.info(f"[_load_strategy] 通过属性检测识别为 Nautilus 策略")

            logger.info(f"[_load_strategy] 策略类 {strategy_class.__name__} 是 Nautilus 策略: {is_nautilus_strategy}")

            if is_nautilus_strategy:
                # Nautilus 格式策略 - 需要创建配置对象
                self.trading_strategy = self._create_nautilus_strategy(strategy_class, module)
            else:
                # 旧格式策略 - 使用字典参数
                strategy_params = self.config.get("params", {})
                self.trading_strategy = strategy_class(strategy_params)

            # 更新状态信息
            self.status.strategy_name = strategy_name or strategy_class.__name__

            # 调用策略初始化
            if hasattr(self.trading_strategy, "on_init"):
                await self._call_strategy_method("on_init")

            logger.info(f"Worker {self.worker_id} 策略加载完成: {strategy_class.__name__}")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 加载策略失败: {e}")
            raise

    def _create_nautilus_strategy(self, strategy_class, module):
        """
        创建 NautilusTrader 原生格式的策略实例

        支持两种 Config 来源：
        1. 策略文件中的自定义 Config 类（优先）- 如 EMACrossConfig
        2. 动态构建通用 Config（兜底）- 当没有专用 Config 时

        关键改进：
        - 使用原生 nautilus_trader.config.StrategyConfig
        - 正确处理 instrument_id (单值) 和 bar_type (BarType 对象)
        - 自动检测并转换字段类型
        """
        import inspect

        logger.info(f"[_create_nautilus] 开始创建策略: {strategy_class.__name__}")

        # ====== Step 1: 获取或创建 Config 类 ======
        config_class = None
        
        # 尝试多种可能的 Config 类名（按优先级排序）
        possible_config_names = [
            f"{strategy_class.__name__}Config",                    # 策略全名 + Config (如 EMACrossStrategyConfig)
            strategy_class.__name__.replace("Strategy", "") + "Config",  # 去掉 Strategy 后缀 (如 GridOrderValidationConfig)
            f"{strategy_class.__name__.split('Strategy')[0]}Config",   # 只取第一部分 + Config
        ]
        
        logger.info(f"[_create_nautilus] 开始查找策略专用 Config 类...")
        
        for config_class_name in possible_config_names:
            logger.info(f"[_create_nautilus] 尝试查找: {config_class_name}")
            
            if hasattr(module, config_class_name):
                config_class = getattr(module, config_class_name)
                logger.info(f"[_create_nautilus] ✅ 找到策略专用 Config 类: {config_class_name}")
                break
            else:
                logger.debug(f"[_create_nautilus] 未找到: {config_class_name}")
        
        if config_class is None:
            # 列出模块中所有包含 "Config" 的类作为参考
            all_classes_in_module = [
                name for name in dir(module)
                if not name.startswith('_') and isinstance(getattr(module, name), type) and 'Config' in name
            ]
            logger.error(
                f"[_create_nautilus] ❌ 未找到任何匹配的 Config 类\n"
                f"[_create_nautilus] 尝试过的名称: {possible_config_names}\n"
                f"[_create_nautilus] 模块中包含'Config'的类: {all_classes_in_module}"
            )

        # ====== Step 2: 从 Worker 配置提取参数 ======
        symbols = self.config.get("symbols", ["BTCUSDT"])
        exchange_raw = self.config.get("exchange", "binance")
        timeframe = self.config.get("timeframe", "1m")
        params = self.config.get("params", {})

        # 处理 exchange 参数（可能是字典或字符串）
        if isinstance(exchange_raw, dict):
            exchange_name = exchange_raw.get("exchange", "binance")
            logger.debug(f"[_create_nautilus] exchange 参数是字典，提取名称: {exchange_name}")
        else:
            exchange_name = str(exchange_raw) if exchange_raw else "binance"

        logger.info(
            f"[_create_nautilus] 提取配置参数: "
            f"symbols={symbols}, exchange={exchange_name}, timeframe={timeframe}"
        )

        # ====== Step 3: 构造 Config 参数 ======
        try:
            if config_class is not None:
                # 使用策略专用的 Config 类（如 EMACrossConfig, GridOrderValidationConfig）
                config = self._build_native_config(
                    config_class, symbols, exchange_name, timeframe, params
                )
            else:
                # 没有找到专用 Config 类
                # 原生 NautilusTrader 策略必须有自己的 Config 子类
                # 如果没有，说明这不是一个标准的原生策略，应该使用旧版 Dict 模式
                logger.error(
                    f"[_create_nautilus] 策略 {strategy_class.__name__} "
                    f"没有找到专用的 Config 类 (期望: {strategy_class.__name__}Config)"
                )
                raise TypeError(
                    f"原生 NautilusTrader 策略 {strategy_class.__name__} "
                    f"必须定义专用的 Config 子类 (继承自 StrategyConfig)，"
                    f"包含 instrument_id 和 bar_type 字段"
                )

            # ====== Step 4: 创建策略实例 ======
            logger.info(f"[_create_nautilus] 正在实例化策略...")
            strategy = strategy_class(config)

            logger.info(
                f"[_create_nautilus] 成功创建策略实例: "
                f"{strategy_class.__name__}, 品种: {symbols}"
            )
            return strategy

        except Exception as e:
            logger.error(f"[_create_nautilus] 创建策略失败: {e}")
            import traceback
            logger.error(f"[_create_nautilus] 异常堆栈:\n{traceback.format_exc()}")
            raise

    def _build_native_config(self, config_class, symbols, exchange, timeframe, params):
        """
        使用策略专用的 Config 类构建配置对象

        处理字段映射和类型转换：
        - Worker 配置中的 symbols (list[str]) → instrument_id (InstrumentId)
        - Worker 配置中的 timeframe (str) → bar_type (BarType)
        - 其他 params 直接传递给 Config

        Parameters
        ----------
        config_class : type
            策略专用的 Config 类（如 EMACrossConfig）
        symbols : list[str]
            交易品种列表（从 Worker 配置获取）
        exchange : str
            交易所标识（如 "binance"）
        timeframe : str
            时间周期（如 "1m", "1h"）
        params : dict
            用户传入的额外策略参数

        Returns
        -------
        config : StrategyConfig
            构建完成的配置对象
        """
        from nautilus_trader.model.identifiers import InstrumentId
        from nautilus_trader.model.data import BarType
        from nautilus_trader.model.enums import PriceType, AggregationSource

        # 构造 instrument_id（取第一个品种，因为原生策略通常只支持单品种）
        symbol = symbols[0] if symbols else "BTCUSDT"
        
        # 清理品种名称：移除 "/" 等特殊字符（如 "ETH/USDT" → "ETHUSDT"）
        clean_symbol = symbol.replace("/", "").replace("-", "")
        
        # 根据 account_type/market_type 决定品种格式
        # 参考 NautilusTrader 的 BinanceSymbol.parse_as_nautilus() 实现:
        # - 现货 (spot): ETHUSDT → "ETHUSDT"
        # - 永续合约 (usdt_futures/futures): ETHUSDT → "ETHUSDT-PERP"
        # - 交割合约 (coin_futures): BTCUSD240628 → "BTCUSD240628" (保持原样)
        exchange_raw = self.config.get("exchange", {})
        
        # 获取账户类型（支持多种字段名）
        account_type = None
        if isinstance(exchange_raw, dict):
            # 尝试多个可能的字段名
            for key in ["account_type", "market_type", "trading_mode"]:
                if exchange_raw.get(key):
                    account_type = str(exchange_raw[key]).lower()
                    logger.info(f"[_build_native_config] 从 '{key}' 获取到交易类型: {account_type}")
                    break
            
            if not account_type:
                account_type = "spot"  # 默认现货
                logger.warning(f"[_build_native_config] 未找到交易类型字段，默认使用: spot")
        else:
            account_type = str(exchange_raw).lower() if exchange_raw else "spot"
        
        logger.info(f"[_build_native_config] 最终使用的交易类型: {account_type}")
        
        # 判断是否是合约模式（更宽松的匹配）
        is_futures = any(keyword in account_type for keyword in [
            "futures", "perp", "swap", "contract", "usdt", "coin"
        ])
        
        # 判断是否是永续合约
        is_perp = any(keyword in account_type for keyword in [
            "_perp", "perpetual", "swap", "usdt_futures", "usdt_perpetual"
        ])
        
        if is_futures and is_perp:
            nautilus_symbol = f"{clean_symbol}-PERP"  # 永续合约: ETHUSDT-PERP
            logger.info(f"[_build_native_config] ✅ 使用永续合约格式: {nautilus_symbol}")
        elif is_futures:
            nautilus_symbol = clean_symbol  # 其他合约
            logger.info(f"[_build_native_config] ✅ 使用合约格式: {nautilus_symbol}")
        else:
            nautilus_symbol = clean_symbol  # 现货
            logger.info(f"[_build_native_config] 使用现货格式: {nautilus_symbol}")
        
        instrument_id = InstrumentId.from_str(f"{nautilus_symbol}.{exchange.upper()}")

        # 构造 bar_type（从时间周期字符串转换，使用完整格式）
        # BarType 完整格式: {SYMBOL}.{EXCHANGE}-{TIMEFRAME}-{PRICE_TYPE}-{AGGREGATION_SOURCE}
        # 例如: ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
        bar_spec = self._convert_timeframe_to_bar_type(timeframe)
        full_bar_type_str = f"{nautilus_symbol}.{exchange.upper()}-{bar_spec}-LAST-{AggregationSource.EXTERNAL.name}"
        bar_type = BarType.from_str(full_bar_type_str)

        # 基础必需参数
        config_kwargs = {
            'instrument_id': instrument_id,
            'bar_type': bar_type,
        }

        # 合并用户传入的额外参数（如 trade_size, fast_ema_period 等）
        # 注意：需要过滤掉无效的参数名
        valid_extra_params = {}
        for key, value in params.items():
            # 过滤掉 Worker 特有的参数，只保留策略参数
            if key not in ['symbols', 'exchange', 'timeframe', 'instrument_ids', 'bar_types',
                          'strategy_code', 'strategy_id', 'strategy_class']:
                valid_extra_params[key] = value

        config_kwargs.update(valid_extra_params)

        logger.info(
            f"[_build_native_config] 构建 {config_class.__name__}:\n"
            f"  - instrument_id: {instrument_id}\n"
            f"  - bar_type: {bar_type}\n"
            f"  - 额外参数: {list(valid_extra_params.keys())}"
        )

        # 创建 Config 实例
        return config_class(**config_kwargs)

    def _build_generic_config(self, strategy_class, symbols, exchange, timeframe, params):
        """
        当策略没有专用 Config 类时，动态构建兼容的 Config 对象

        通过检查策略 __init__ 签名推断所需参数，
        并使用原生 StrategyConfig 作为基类。

        Parameters
        ----------
        strategy_class : type
            策略类
        symbols : list[str]
            交易品种列表
        exchange : str
            交易所标识
        timeframe : str
            时间周期
        params : dict
            额外策略参数

        Returns
        -------
        config : StrategyConfig
            通用配置对象
        """
        from decimal import Decimal
        import inspect
        from nautilus_trader.model.identifiers import InstrumentId
        from nautilus_trader.model.data import BarType
        from nautilus_trader.config import StrategyConfig as NativeStrategyConfig

        # 构造基础参数
        symbol = symbols[0] if symbols else "BTCUSDT"
        # 清理品种名称：移除 "/" 等特殊字符（如 "ETH/USDT" → "ETHUSDT"）
        clean_symbol = symbol.replace("/", "").replace("-", "")
        instrument_id = InstrumentId.from_str(f"{clean_symbol}.{exchange.upper()}")

        # 构造 bar_type（从时间周期字符串转换，使用完整格式）
        # BarType 完整格式: {SYMBOL}.{EXCHANGE}-{TIMEFRAME}-{PRICE_TYPE}-{AGGREGATION_SOURCE}
        from nautilus_trader.model.enums import PriceType, AggregationSource
        bar_spec = self._convert_timeframe_to_bar_type(timeframe)
        full_bar_type_str = f"{clean_symbol}.{exchange.upper()}-{bar_spec}-LAST-{AggregationSource.EXTERNAL.name}"
        bar_type = BarType.from_str(full_bar_type_str)

        # 检查策略 __init__ 需要哪些参数（除了 self 和 config）
        # 注意：Cython 编译的类可能无法获取签名
        init_params = []
        try:
            init_signature = inspect.signature(strategy_class.__init__)
            init_params = [
                name for name in init_signature.parameters.keys()
                if name not in ('self', 'config')
            ]
        except (ValueError, TypeError) as e:
            logger.warning(
                f"[_build_generic_config] 无法获取 {strategy_class.__name__} 的 __init__ 签名: {e}\n"
                f"将只使用基础配置参数（instrument_id, bar_type）和用户传入的额外参数"
            )

        logger.info(f"[_build_generic_config] 策略 __init__ 额外参数: {init_params}")

        # 构建配置字典
        config_dict = {
            'instrument_id': instrument_id,
            'bar_type': bar_type,
        }

        # 如果策略需要 trade_size
        if 'trade_size' in init_params or 'order_size' in init_params:
            size_key = 'trade_size' if 'trade_size' in init_params else 'order_size'
            size_value = params.get('order_size', params.get('trade_size', '0.001'))
            config_dict[size_key] = Decimal(str(size_value))

        # 传递其他可能的参数
        for key, value in params.items():
            if key not in ['instrument_id', 'bar_type', 'trade_size', 'order_size',
                         'symbols', 'exchange', 'timeframe']:
                if key in init_params:
                    config_dict[key] = value

        logger.info(f"[_build_generic_config] 最终配置字典: {list(config_dict.keys())}")

        return NativeStrategyConfig(**config_dict)

    def _convert_timeframe_to_bar_type(self, timeframe: str) -> str:
        """
        将时间周期转换为 Nautilus bar type 格式

        e.g., "1m" -> "1-MINUTE", "1h" -> "1-HOUR"
        """
        unit_map = {
            "m": "MINUTE",
            "h": "HOUR",
            "d": "DAY",
            "w": "WEEK",
            "M": "MONTH",
        }

        if not timeframe:
            return "1-HOUR"

        # 解析时间周期 (e.g., "1h", "15m")
        import re
        match = re.match(r"(\d+)([mhdwM])", timeframe)
        if match:
            value, unit = match.groups()
            bar_type = f"{value}-{unit_map.get(unit, 'HOUR')}"
            return bar_type

        return "1-HOUR"

    async def _subscribe_data(self):
        """
        订阅市场数据
        """
        symbols = self.config.get("symbols", [])
        data_types = self.config.get("data_types", ["kline"])

        if symbols and self.comm_client:
            success = self.comm_client.subscribe_symbols(symbols, data_types)
            if success:
                logger.info(f"Worker {self.worker_id} 已订阅: symbols={symbols}, types={data_types}")
            else:
                logger.warning(f"Worker {self.worker_id} 订阅数据部分失败")

    async def _handle_data(self, topic: str, message: Message):
        """
        处理市场数据

        Args:
            topic: 数据主题
            message: 数据消息
        """
        try:
            if self.status.state != WorkerState.RUNNING:
                return

            # 更新统计
            self._messages_processed += 1
            self.status.messages_processed = self._messages_processed

            # 解析数据
            symbol = message.payload.get("symbol")
            data_type = message.payload.get("data_type")
            data = message.payload.get("data")

            if not symbol or not data:
                return

            # 调用策略回调
            if data_type == "kline" and hasattr(self.trading_strategy, "on_bar"):
                await self._call_strategy_method("on_bar", data)
            elif data_type == "tick" and hasattr(self.trading_strategy, "on_tick"):
                await self._call_strategy_method("on_tick", data)

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 处理数据错误: {e}")
            self.status.record_error(str(e))

    async def _handle_control(self, message: Message):
        """
        处理控制命令

        Args:
            message: 控制消息
        """
        try:
            logger.info(f"Worker {self.worker_id} 收到控制命令: {message.msg_type.value}")

            if message.msg_type == MessageType.STOP:
                await self._handle_stop()
            elif message.msg_type == MessageType.RELOAD_CONFIG:
                await self._handle_reload_config(message.payload)
            elif message.msg_type == MessageType.UPDATE_PARAMS:
                await self._handle_update_params(message.payload)
            else:
                logger.warning(f"未知的控制命令: {message.msg_type.value}")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 处理控制命令错误: {e}")
            self.status.record_error(str(e))

    async def _handle_stop(self):
        """处理停止命令"""
        logger.info(f"[WorkerProcess] Worker {self.worker_id} 收到停止命令，准备停止...")
        self.status.update_state(WorkerState.STOPPING)
        await self._send_status(MessageType.STATUS_UPDATE)
        logger.info(f"[WorkerProcess] Worker {self.worker_id} 设置 _shutdown_event")
        self._shutdown_event.set()
        logger.info(f"[WorkerProcess] Worker {self.worker_id} _shutdown_event 已设置")

    async def _handle_reload_config(self, config: Dict[str, Any]):
        """处理重载配置命令"""
        logger.info(f"Worker {self.worker_id} 收到重载配置命令")
        self.status.update_state(WorkerState.RELOADING)
        self.config.update(config)
        # 重新订阅数据
        await self._subscribe_data()
        self.status.update_state(WorkerState.RUNNING)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _handle_update_params(self, params: Dict[str, Any]):
        """处理更新参数命令"""
        logger.info(f"Worker {self.worker_id} 收到更新参数命令")
        if self.trading_strategy and hasattr(self.trading_strategy, "update_params"):
            await self._call_strategy_method("update_params", params)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _call_strategy_method(self, method_name: str, *args, **kwargs):
        """
        安全调用策略方法

        包装策略方法调用，捕获异常防止策略错误导致 Worker 崩溃
        """
        if not self.trading_strategy:
            return

        try:
            method = getattr(self.trading_strategy, method_name, None)
            if method is None:
                return

            # 检查是否是协程函数
            if asyncio.iscoroutinefunction(method):
                return await method(*args, **kwargs)
            else:
                return method(*args, **kwargs)

        except Exception as e:
            logger.error(f"策略方法 {method_name} 执行错误: {e}")
            self.status.record_error(f"{method_name}: {str(e)}")
            # 不抛出异常，防止 Worker 崩溃

    async def _sync_orders_from_nautilus(self):
        """
        从 NautilusTrader Cache 同步活跃委托到本地数据库

        核心逻辑：
        1. 调用 trader.cache.orders_open() 获取所有未成交订单
        2. 将每个 Order 对象转换为 WorkerOrder 记录
        3. 使用 upsert 策略（存在则更新，不存在则插入）
        """
        if not hasattr(self, 'trader') or not self.trader:
            return

        try:
            from datetime import datetime

            # 获取所有开放的订单（未完全成交）
            open_orders = self.trader.cache.orders_open()

            for order in open_orders:
                try:
                    order_data = {
                        'client_order_id': str(order.client_order_id),
                        'venue_order_id': str(order.venue_order_id) if order.venue_order_id else None,
                        'symbol': str(order.instrument_id.symbol),
                        'side': str(order.side).upper(),
                        'order_type': str(order.order_type).lower(),
                        'quantity': float(order.quantity),
                        'price': float(order.price) if order.price else None,
                        'filled_qty': float(order.filled_qty),
                        'avg_fill_price': float(order.avg_fill_price) if hasattr(order, 'avg_fill_price') else 0.0,
                        'status': 'OPEN' if order.is_open_c() else str(order.status).upper(),
                        'position_id': str(order.position_id) if order.position_id else None,
                        'worker_id': self.worker_id,
                        'updated_at': datetime.utcnow(),
                    }

                    # 保存到内存队列，后续批量持久化
                    if not hasattr(self, '_pending_orders_to_sync'):
                        self._pending_orders_to_sync = []
                    self._pending_orders_to_sync.append(order_data)

                except Exception as e:
                    logger.warning(f"[{self.worker_id}] 处理订单 {order.client_order_id} 失败: {e}")

            logger.debug(f"[{self.worker_id}] 同步了 {len(open_orders)} 个活跃委托")

        except Exception as e:
            logger.error(f"[{self.worker_id}] 同步委托失败: {e}")

    async def _sync_positions_from_nautilus(self):
        """
        从 NautilusTrader Cache 同步当前持仓到本地数据库

        核心逻辑：
        1. 调用 trader.cache.positions_open() 获取所有当前持仓
        2. 将每个 Position 对象转换为 WorkerPosition 记录
        3. 使用 upsert 策略
        """
        if not hasattr(self, 'trader') or not self.trader:
            return

        try:
            from datetime import datetime

            # 获取所有开放的持仓
            open_positions = self.trader.cache.positions_open()

            for position in open_positions:
                try:
                    pos_data = {
                        'position_id': str(position.position_id),
                        'symbol': str(position.instrument_id.symbol),
                        'side': str(position.side).upper(),
                        'quantity': abs(float(position.quantity)),
                        'entry_price': float(position.avg_entry_open) if hasattr(position, 'avg_entry_open') else float(position.entry_price) if hasattr(position, 'entry_price') else 0.0,
                        'current_price': None,
                        'unrealized_pnl': float(position.unrealized_pnl()) if hasattr(position, 'unrealized_pnl') and callable(position.unrealized_pnl) else 0.0,
                        'realized_pnl': float(position.realized_pnl) if hasattr(position, 'realized_pnl') else 0.0,
                        'status': 'OPEN',
                        'opened_at': position.opened_time if hasattr(position, 'opened_time') else datetime.utcnow(),
                        'worker_id': self.worker_id,
                        'updated_at': datetime.utcnow(),
                    }

                    # 保存到内存队列，后续批量持久化
                    if not hasattr(self, '_pending_positions_to_sync'):
                        self._pending_positions_to_sync = []
                    self._pending_positions_to_sync.append(pos_data)

                except Exception as e:
                    logger.warning(f"[{self.worker_id}] 处理持仓 {position.position_id} 失败: {e}")

            logger.debug(f"[{self.worker_id}] 同步了 {len(open_positions)} 个持仓")

        except Exception as e:
            logger.error(f"[{self.worker_id}] 同步持仓失败: {e}")

    async def _send_heartbeat(self):
        """发送心跳消息"""
        self.status.update_heartbeat()
        await self._send_status(MessageType.HEARTBEAT)

    async def _send_status(self, msg_type: MessageType) -> bool:
        """
        发送状态消息

        Args:
            msg_type: 消息类型

        Returns:
            是否发送成功
        """
        if self.comm_client:
            # 调试：记录消息创建时的详细信息（仅debug级别）
            status_dict = self.status.to_dict()
            logger.debug(f"[_send_status] 创建消息: worker_id={self.worker_id}, msg_type={msg_type}, state={self.status.state.name}")
            logger.debug(f"[_send_status] status_dict: {status_dict}")

            message = Message(
                msg_type=msg_type,
                worker_id=self.worker_id,
                payload=status_dict,
            )
            logger.debug(f"[_send_status] 消息对象: worker_id={message.worker_id}, msg_type={message.msg_type}")

            result = await self.comm_client.send_status(message)
            logger.debug(f"[_send_status] Worker {self.worker_id} 状态消息发送结果: {result}")
            return result
        else:
            logger.warning(f"[_send_status] Worker {self.worker_id} comm_client 为 None，无法发送状态")
            return False

    def _handle_signal(self, signum, frame):
        """
        处理系统信号

        改进：标记需要优雅停止，让主循环退出后执行完整的 Nautilus 停止流程

        Args:
            signum: 信号编号
            frame: 当前栈帧
        """
        logger.info(f"Worker {self.worker_id} 收到信号 {signum}，请求优雅停止")
        self._graceful_stop_requested = True  # 标记需要优雅停止
        self._shutdown_event.set()

    async def _cleanup(self):
        """
        清理资源

        清理顺序：
        1. 调用策略 on_stop()
        2. 断开通信连接
        3. 更新状态为 STOPPED
        """
        logger.info(f"Worker {self.worker_id} 开始清理资源")

        # 调用策略清理方法
        if self.trading_strategy and hasattr(self.trading_strategy, "on_stop"):
            try:
                await self._call_strategy_method("on_stop")
            except Exception as e:
                logger.error(f"Worker {self.worker_id} 策略清理错误: {e}")

        # 断开通信连接（使用超时避免阻塞）
        if self.comm_client:
            try:
                import asyncio
                await asyncio.wait_for(self.comm_client.disconnect(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Worker {self.worker_id} 断开通信连接超时")
            except Exception as e:
                logger.error(f"Worker {self.worker_id} 断开通信连接错误: {e}")

        # 更新状态
        self.status.update_state(WorkerState.STOPPED)
        logger.info(f"Worker {self.worker_id} 资源清理完成，进程即将退出")

    def stop(self):
        """
        请求停止 Worker（在主进程中调用）
        """
        self._shutdown_event.set()

    def is_running(self) -> bool:
        """
        检查 Worker 是否正在运行

        Returns:
            是否正在运行
        """
        return self.is_alive() and not self._shutdown_event.is_set()


# =============================================================================
# 余额检查器
# =============================================================================

class BalanceChecker:
    """
    余额检查器

    检查账户余额是否充足，并在余额不足时提供自动调整功能。
    """

    def __init__(
        self,
        trader: Any,
        min_balance_buffer: float = 1.1,  # 10% 缓冲
        auto_adjust: bool = False,
    ):
        """
        初始化余额检查器

        Parameters
        ----------
        trader : Any
            Nautilus Trader 实例
        min_balance_buffer : float
            最小余额缓冲系数（默认 1.1 = 10% 缓冲）
        auto_adjust : bool
            是否自动调整订单数量
        """
        self.trader = trader
        self.min_balance_buffer = min_balance_buffer
        self.auto_adjust = auto_adjust

    def check_balance(
        self,
        instrument_id: Any,
        order_qty: Decimal,
        price: float | None = None,
    ) -> tuple[bool, str, Decimal | None]:
        """
        检查账户余额是否充足

        Parameters
        ----------
        instrument_id : Any
            交易品种标识符
        order_qty : Decimal
            订单数量
        price : float | None
            当前价格（如果为 None，则尝试从缓存获取）

        Returns
        -------
        tuple[bool, str, Decimal | None]
            (是否充足, 消息, 调整后数量)
            - 如果余额充足，返回 (True, "余额充足", None)
            - 如果余额不足且 auto_adjust=False，返回 (False, 错误消息, None)
            - 如果余额不足且 auto_adjust=True，返回 (True, 警告消息, 调整后数量)
        """
        try:
            # 获取账户
            account = self.trader.portfolio.account(instrument_id.venue)
            if account is None:
                return True, "无法获取账户信息，跳过余额检查", None

            # 获取当前价格
            if price is None:
                price = self._get_current_price(instrument_id)
                if price is None:
                    return True, "无法获取当前价格，跳过余额检查", None

            # 计算所需余额
            required_balance = float(order_qty) * price * self.min_balance_buffer

            # 获取可用余额
            free_balance = self._get_free_balance(account, instrument_id)

            if free_balance < required_balance:
                shortfall = required_balance - free_balance
                error_msg = (
                    f"余额不足！缺少 {shortfall:.4f} USDT\n"
                    f"可用: {free_balance:.4f} USDT\n"
                    f"所需: {required_balance:.4f} USDT\n"
                    f"当前价格: {price:.2f}"
                )

                if self.auto_adjust:
                    # 自动调整订单数量
                    new_qty = self._calculate_adjusted_qty(
                        free_balance, price, instrument_id
                    )
                    if new_qty is not None and new_qty > 0:
                        warning_msg = (
                            f"{error_msg}\n"
                            f"已自动调整订单数量: {order_qty} -> {new_qty}"
                        )
                        return True, warning_msg, new_qty
                    else:
                        error_msg += "\n即使调整后数量仍不足，无法下单"
                        return False, error_msg, None
                else:
                    error_msg += "\n建议：1) 给账户充值 2) 减小订单数量 3) 启用自动调整"
                    return False, error_msg, None

            return True, f"余额充足 - 可用: {free_balance:.4f} USDT, 所需: {required_balance:.4f} USDT", None

        except Exception as e:
            return True, f"余额检查出错: {e}，默认继续", None

    def _get_current_price(self, instrument_id: Any) -> float | None:
        """获取当前价格"""
        try:
            # 尝试从缓存获取报价
            quote = self.trader.cache.quote_tick(instrument_id)
            if quote:
                return float(quote.ask_price)

            # 尝试从缓存获取最新价格
            bar = self.trader.cache.bar(instrument_id)
            if bar:
                return float(bar.close)

            return None
        except Exception:
            return None

    def _get_free_balance(self, account, instrument_id: Any) -> float:
        """获取可用余额"""
        try:
            balances = account.balances()
            free_balance = 0.0

            for balance in balances:
                currency_code = balance.currency.code
                # 尝试找到计价货币（如 USDT）的余额
                if currency_code in ("USDT", "USD", "BUSD", "USDC"):
                    free_balance = float(balance.free)
                    break

            return free_balance
        except Exception:
            return 0.0

    def _calculate_adjusted_qty(
        self,
        free_balance: float,
        price: float,
        instrument_id: Any,
    ) -> Decimal | None:
        """计算调整后的订单数量"""
        try:
            # 计算最大可下单数量（留 10% 缓冲）
            max_qty = free_balance / price / self.min_balance_buffer

            # 获取交易品种信息以检查最小交易量
            instrument = self.trader.cache.instrument(instrument_id)
            if instrument:
                min_qty = float(instrument.min_quantity)
                # 确保不小于最小交易量
                if max_qty < min_qty:
                    return None

            return Decimal(str(max_qty))
        except Exception:
            return None


def check_balance_before_trade(
    trader: Any,
    instrument_id: Any,
    order_qty: Decimal,
    auto_adjust: bool = False,
) -> tuple[bool, str, Decimal | None]:
    """
    交易前检查余额的便捷函数

    Parameters
    ----------
    trader : Any
        Nautilus Trader 实例
    instrument_id : Any
        交易品种标识符
    order_qty : Decimal
        订单数量
    auto_adjust : bool
        是否自动调整订单数量

    Returns
    -------
    tuple[bool, str, Decimal | None]
        (是否充足, 消息, 调整后数量)
    """
    checker = BalanceChecker(trader, auto_adjust=auto_adjust)
    return checker.check_balance(instrument_id, order_qty)


# =============================================================================
# TradingNode Worker 进程（支持 Nautilus Trader）
# =============================================================================

# 尝试导入 Nautilus 相关类
try:
    from nautilus_trader.live.node import TradingNode
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    TradingNode = None


class TradingNodeWorkerProcess(WorkerProcess):
    """
    TradingNode Worker 进程

    在完全隔离的 Python 进程中运行基于 TradingNode 的策略，
    通过进程间通信与主进程进行交互。

    这是 WorkerProcess 的扩展，专门用于支持 Nautilus Trader 框架。
    """

    def __init__(
        self,
        worker_id: str,
        strategy_path: str,
        config: Dict[str, Any],
        comm_host: str = "127.0.0.1",
        data_port: Optional[int] = None,
        control_port: Optional[int] = None,
        status_port: Optional[int] = None,
    ):
        super().__init__(
            worker_id=worker_id,
            strategy_path=strategy_path,
            config=config,
            comm_host=comm_host,
            data_port=data_port,
            control_port=control_port,
            status_port=status_port,
        )

        # TradingNode 相关属性
        self.trading_node: Optional[Any] = None
        self.trading_strategy: Optional[Any] = None
        self.event_handler: Optional[Any] = None
        self.trading_config: Dict[str, Any] = {}

        # NautilusTrader 日志系统的 LogGuard（防止被垃圾回收）
        self._nautilus_log_guard: Optional[Any] = None

        # 从配置中提取 TradingNode 特定配置
        self._extract_trading_config()

    def _extract_trading_config(self):
        """从配置中提取 TradingNode 特定配置"""
        self.trading_config = self.config.get("trading", self.config.get("nautilus", {}))
        logger.debug(f"Worker {self.worker_id} TradingNode 配置: {self.trading_config}")

    async def _main_loop(self):
        """
        主事件循环 - 重写以支持 TradingNode
        """
        if not NAUTILUS_AVAILABLE:
            logger.warning("Nautilus Trader 未安装，使用标准 Worker 模式")
            await super()._main_loop()
            return

        try:
            # 1. 初始化通信连接
            await self._init_comm()

            # 2. 初始化 TradingNode
            self.trading_node = await self._init_trading_node()
            if self.trading_node is None:
                raise RuntimeError("无法初始化 TradingNode")

            # 3. 加载策略
            await self._load_trading_strategy()

            # 3.5 将策略注册到 TradingNode（通过 Trader 对象）
            if self.trading_strategy is not None:
                logger.info(f"Worker {self.worker_id} 将策略注册到 TradingNode...")
                try:
                    # ✅ 正确：通过 trader 属性访问 add_strategy 方法
                    # 参考 NautilusTrader 官方示例: node.trader.add_strategy(strategy)
                    self.trading_node.trader.add_strategy(self.trading_strategy)
                    logger.info(
                        f"Worker {self.worker_id} 策略已成功注册到 TradingNode: "
                        f"{type(self.trading_strategy).__name__}"
                    )
                except Exception as e:
                    logger.error(
                        f"Worker {self.worker_id} 注册策略到 TradingNode 失败: {e}"
                    )
                    raise
            else:
                logger.error(f"Worker {self.worker_id} 策略加载失败，trading_strategy 为 None!")
                raise RuntimeError("策略加载失败")

            # 4. 启动 TradingNode
            await self._handle_start()

            logger.info(f"Worker {self.worker_id} TradingNode 启动完成，开始运行")

            # 4.5 注册交易事件监听器
            self._setup_trade_event_handlers()

            # 5. 主循环 - 等待关闭信号
            check_count = 0
            save_interval_counter = 0
            while not self._shutdown_event.is_set():
                check_count += 1

                # 每10秒同步一次委托和持仓状态（新增）
                if check_count % 10 == 0:
                    await self._sync_orders_from_nautilus()
                    await self._sync_positions_from_nautilus()

                # 每30秒触发一次数据持久化（备份机制）
                save_interval_counter += 1
                if save_interval_counter >= 30:
                    await self._save_pending_trades_to_db()
                    save_interval_counter = 0

                # 发送心跳
                await self._send_heartbeat()

                # 等待一段时间
                await asyncio.sleep(1)

            # 6. 主循环结束，保存剩余交易记录
            logger.info(f"[{self.worker_id}] 正在保存最后的交易记录...")
            await self._save_pending_trades_to_db()

            # 7. 停止 Nautilus 运行任务
            if hasattr(self, '_nautilus_run_task') and self._nautilus_run_task:
                logger.info(f"Worker {self.worker_id} 正在停止 Nautilus 运行任务...")
                self._nautilus_run_task.cancel()
                try:
                    await asyncio.wait_for(self._nautilus_run_task, timeout=10.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                logger.info(f"Worker {self.worker_id} Nautilus 运行任务已停止")

        except asyncio.CancelledError:
            logger.info(f"Worker {self.worker_id} 控制循环被取消，正在优雅退出")
            await self._save_pending_trades_to_db()
        except Exception as e:
            logger.error(f"Worker {self.worker_id} 主循环异常: {e}")
            try:
                await self._save_pending_trades_to_db()
            except:
                pass
            self.status.update_state(WorkerState.ERROR)
            self.status.record_error(str(e))
            await self._send_status(MessageType.ERROR)
            raise

    async def _init_trading_node(self) -> Optional[Any]:
        """初始化 TradingNode"""
        if not NAUTILUS_AVAILABLE:
            return None

        try:
            logger.info(f"Worker {self.worker_id} 开始初始化 TradingNode")

            # 导入配置构建器
            from .config import (
                build_trading_node_config,
                validate_config,
            )

            # 从配置中提取参数
            exchange = self.trading_config.get("exchange", "binance")
            account_type = self.trading_config.get("account_type", "spot")
            trading_mode = self.trading_config.get("trading_mode", "demo")
            proxy_url = self.trading_config.get("proxy_url")
            api_key = self.trading_config.get("api_key")
            api_secret = self.trading_config.get("api_secret")
            api_passphrase = self.trading_config.get("api_passphrase")
            
            # 默认使用 DEBUG 级别以便调试 NautilusTrader 日志问题
            log_level = self.trading_config.get("log_level", "DEBUG")

            # 配置日志目录 — 让 NautilusTrader 日志直接写到 backend/logs/
            from pathlib import Path
            log_directory = self.trading_config.get("log_directory")
            if not log_directory:
                log_directory = str(Path(__file__).parent.parent / "logs")
            log_file_name = self.trading_config.get("log_file_name", f"worker_{self.worker_id}.log")

            # 验证配置
            is_valid, error_msg = validate_config(
                exchange=exchange,
                trading_mode=trading_mode,
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
            )
            if not is_valid:
                logger.error(f"Worker {self.worker_id} 配置验证失败: {error_msg}")
                self.status.record_error(f"配置验证失败: {error_msg}")
                return None

            # 构建配置（LoggingConfig 由 build_trading_node_config 内部创建）
            node_config, (data_factory, exec_factory, venue) = build_trading_node_config(
                exchange=exchange,
                account_type=account_type,
                trading_mode=trading_mode,
                trader_id=f"WORKER-{self.worker_id}",
                log_level=log_level,
                proxy_url=proxy_url,
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
                log_directory=log_directory,
                log_file_name=log_file_name,
            )

            # 创建 TradingNode 实例
            trading_node = TradingNode(config=node_config)

            # 注册客户端工厂
            trading_node.add_data_client_factory(venue, data_factory)
            trading_node.add_exec_client_factory(venue, exec_factory)

            # 构建节点（此时 TradingNodeConfig 中的 LoggingConfig 会自动初始化日志系统）
            logger.info(f"Worker {self.worker_id} 正在构建 TradingNode（日志系统将在此步骤初始化）...")
            trading_node.build()

            # 验证日志配置
            self._verify_logging_config()

            logger.info(f"Worker {self.worker_id} TradingNode 初始化完成")
            return trading_node

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 初始化 TradingNode 失败: {e}")
            self.status.record_error(f"初始化失败: {str(e)}")
            return None

    def _verify_logging_config(self) -> None:
        """验证 NautilusTrader 日志系统配置

        在 TradingNode.build() 完成后调用，
        验证日志文件路径并输出详细的配置信息用于调试。
        """
        try:
            from pathlib import Path

            log_path = Path(__file__).parent.parent / "logs" / f"worker_{self.worker_id}.log"

            logger.info(
                f"Worker {self.worker_id} NautilusTrader 日志配置:\n"
                f"  - 日志文件: {log_path}\n"
                f"  - 日志目录: {self.trading_config.get('log_directory')}\n"
                f"  - 文件名: {self.trading_config.get('log_file_name')}\n"
                f"  - 日志级别: {self.trading_config.get('log_level')}"
            )

            if log_path.exists():
                file_size = log_path.stat().st_size
                logger.info(
                    f"Worker {self.worker_id} 日志文件已存在 (大小: {file_size} bytes)"
                )
            else:
                logger.info(
                    f"Worker {self.worker_id} 日志文件将在 TradingNode 启动时创建"
                )

        except Exception as e:
            logger.warning(f"Worker {self.worker_id} 验证日志配置失败: {e}")

    def _setup_trade_event_handlers(self):
        """
        注册 NautilusTrader 事件处理器以捕获交易数据

        订阅 MessageBus 的订单事件，将 OrderFilled 转换为内部格式
        """
        if not hasattr(self, 'trading_node') or not self.trading_node:
            logger.warning(f"[{self.worker_id}] TradingNode 未初始化，跳过事件注册")
            return

        try:
            kernel = self.trading_node.kernel
            msgbus = kernel.msgbus

            msgbus.subscribe(
                topic="events.order.*",
                handler=self._on_nautilus_order_event,
                priority=20
            )

            logger.info(f"[{self.worker_id}] 已成功注册 NautilusTrader 事件监听器")

        except Exception as e:
            logger.error(f"[{self.worker_id}] 注册事件监听器失败: {e}")

    def _on_nautilus_order_event(self, event):
        """
        处理来自 NautilusTrader 的订单事件

        Parameters
        ----------
        event : OrderEvent
            NautilusTrader 的订单事件对象
        """
        try:
            event_type_name = type(event).__name__

            if event_type_name == "OrderFilled":
                self._process_order_filled_event(event)
            else:
                logger.debug(
                    f"[{self.worker_id}] 收到订单事件: {event_type_name}, "
                    f"order_id={getattr(event, 'client_order_id', 'N/A')}"
                )

        except Exception as e:
            logger.error(f"[{self.worker_id}] 处理订单事件异常: {e}", exception=e)

    def _process_order_filled_event(self, event):
        """
        处理 OrderFilled 事件 - 核心数据提取逻辑

        将 NautilusTrader 的 OrderFilled 对象转换为标准字典格式，
        并存储到内存缓存中供后续持久化使用。
        """
        try:
            from nautilus_trader.model.enums import order_side_to_str, order_type_to_str

            def safe_str(attr):
                if attr is None:
                    return None
                return str(attr)

            def safe_float(attr):
                if attr is None:
                    return 0.0
                try:
                    return float(attr)
                except (TypeError, ValueError):
                    return 0.0

            trade_record = {
                "trade_id": safe_str(getattr(event, 'trade_id', None)),
                "client_order_id": safe_str(getattr(event, 'client_order_id', None)),
                "venue_order_id": safe_str(getattr(event, 'venue_order_id', None)),
                "instrument_id": safe_str(getattr(event, 'instrument_id', None)),
                "symbol": self._extract_symbol_from_instrument_id(
                    safe_str(getattr(event, 'instrument_id', None))
                ),
                "order_side": order_side_to_str(getattr(event, 'order_side', None)).upper(),
                "order_type": order_type_to_str(getattr(event, 'order_type', None)).lower(),
                "quantity": safe_float(getattr(event, 'last_qty', None)),
                "price": safe_float(getattr(event, 'last_px', None)),
                "amount": safe_float(getattr(event, 'last_qty', None)) * safe_float(getattr(event, 'last_px', None)),
                "commission": safe_float(getattr(event, 'commission', None)),
                "currency": safe_str(getattr(event, 'currency', None)) or "USDT",
                "liquidity_side": safe_str(getattr(event, 'liquidity_side', None)),
                "account_id": safe_str(getattr(event, 'account_id', None)),
                "strategy_id": safe_str(getattr(event, 'strategy_id', None)),
                "position_id": safe_str(getattr(event, 'position_id', None)),
                "ts_event": getattr(event, 'ts_event', 0),
                "ts_init": getattr(event, 'ts_init', 0),
                "created_at": datetime.utcnow().isoformat(),
                "source": "nautilus_live",
                "worker_id": str(self.worker_id),
            }

            self._trade_records.append(trade_record)

            if len(self._trade_records) > self._max_trade_records:
                self._trade_records = self._trade_records[-self._max_trade_records:]

            logger.info(
                f"[{self.worker_id}] 捕获成交记录: "
                f"{trade_record['order_side']} {trade_record['quantity']} {trade_record['symbol']} "
                f"@ {trade_record['price']} {trade_record['currency']}"
            )

            self._trigger_trade_persistence()

        except Exception as e:
            logger.error(f"[{self.worker_id}] 处理 OrderFilled 事件失败: {e}", exception=e)

    def _extract_symbol_from_instrument_id(self, instrument_id: str) -> str:
        """
        从 InstrumentId 中提取交易对符号

        Example:
            "ETHUSDT-PERP.BINANCE" -> "ETHUSDT"
            "BTCUSDT.BINANCE" -> "BTCUSDT"
        """
        if not instrument_id:
            return "UNKNOWN"

        parts = instrument_id.split('.')
        base = parts[0] if parts else instrument_id

        symbol = base.split('-')[0]

        return symbol

    def _trigger_trade_persistence(self):
        """
        触发交易记录持久化（带节流控制）

        避免频繁写入数据库，采用以下策略：
        - 首次立即保存
        - 后续每30秒批量保存一次
        - 进程退出时强制保存
        """
        import time
        current_time = time.time()

        if current_time - self._last_save_time >= 30 or self._last_save_time == 0.0:
            asyncio.create_task(self._save_pending_trades_to_db())
            self._last_save_time = current_time

    async def _save_pending_trades_to_db(self):
        """
        将待保存的交易记录批量写入数据库

        使用异步操作避免阻塞主循环
        """
        if not hasattr(self, '_trade_records') or not self._trade_records:
            return

        try:
            from worker.models import WorkerTrade
            from collector.db.database import SessionLocal

            records_to_save = [r.copy() for r in self._trade_records]

            if not records_to_save:
                return

            db = SessionLocal()
            try:
                saved_count = 0

                for record in records_to_save:
                    existing = db.query(WorkerTrade).filter(
                        WorkerTrade.trade_id == record.get('trade_id')
                    ).first()

                    if existing:
                        continue

                    trade = WorkerTrade(
                        worker_id=int(self.worker_id),
                        trade_id=record.get('trade_id') or f"GEN-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
                        symbol=record.get('symbol', 'UNKNOWN'),
                        side=record.get('order_side', 'buy').lower(),
                        order_type=record.get('order_type', 'limit'),
                        quantity=record.get('quantity', 0.0),
                        price=record.get('price', 0.0),
                        amount=record.get('amount', 0.0),
                        fee=record.get('commission', 0.0),
                        fee_currency=record.get('currency', 'USDT'),
                        created_at=datetime.fromisoformat(record['created_at']) if record.get('created_at') else datetime.utcnow(),
                        raw_data=json.dumps(record, ensure_ascii=False, default=str),
                    )

                    db.add(trade)
                    saved_count += 1

                db.commit()

                if saved_count > 0:
                    logger.info(
                        f"[{self.worker_id}] 已成功保存 {saved_count} 条交易记录到数据库"
                    )

            except Exception as e:
                db.rollback()
                logger.error(f"[{self.worker_id}] 保存交易记录到数据库失败: {e}", exception=e)
            finally:
                db.close()

        except ImportError as e:
            logger.warning(f"[{self.worker_id}] 无法导入数据库模块: {e}")
        except Exception as e:
            logger.error(f"[{self.worker_id}] 持久化任务异常: {e}", exception=e)

    async def _load_trading_strategy(self):
        """加载策略

        支持三种方式加载策略（与基类 _load_strategy 保持一致）：
        1. config 中的 strategy_code（优先）
        2. 数据库中的策略代码（回退）
        3. 文件路径加载（最后回退）
        """
        try:
            import importlib.util
            import sys
            import types

            strategy_code: Optional[str] = None
            strategy_name: Optional[str] = None
            module = None

            # 方式1: 优先从 config 获取策略代码
            strategy_code = self.config.get("strategy_code")
            if strategy_code:
                logger.info(f"Worker {self.worker_id} 使用从配置传递的策略代码")

            # 方式2: 从数据库加载策略代码
            if not strategy_code:
                try:
                    from collector.db.database import init_database_config, SessionLocal
                    from strategy.models import Strategy

                    init_database_config()
                    db = SessionLocal()
                    try:
                        strategy_id = self.config.get("strategy_id")
                        if strategy_id:
                            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
                            if strategy is not None:
                                code = getattr(strategy, 'code', None)
                                name = getattr(strategy, 'name', None)
                                if code:
                                    strategy_code = str(code)
                                    strategy_name = str(name) if name else None
                                    logger.info(f"Worker {self.worker_id} 从数据库加载策略: {name}")
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"Worker {self.worker_id} 从数据库加载策略失败: {e}")

            # 方式3: 从文件路径加载
            if not strategy_code and self.strategy_path:
                if os.path.exists(self.strategy_path):
                    with open(self.strategy_path, 'r', encoding='utf-8') as f:
                        strategy_code = f.read()
                    logger.info(f"Worker {self.worker_id} 从文件加载策略: {self.strategy_path}")
                else:
                    raise ImportError(f"策略文件不存在: {self.strategy_path}")

            if not strategy_code:
                raise ImportError("策略代码为空（strategy_code=None 且无可用文件路径）")

            # 动态创建模块并执行策略代码
            module_name = f"trading_strategy_{self.worker_id}"
            module = types.ModuleType(module_name)
            sys.modules[module_name] = module
            exec(strategy_code, module.__dict__)

            # 获取策略类（排除抽象基类，自动发现具体子类）
            from strategy.core import StrategyBase

            strategy_class_name = self.config.get("strategy_class")
            strategy_class = None

            # 如果明确指定了策略类名，尝试获取
            if strategy_class_name:
                strategy_class = getattr(module, strategy_class_name, None)
                
                # 验证获取的类是否为有效的具体策略类（非抽象基类）
                if strategy_class is not None and isinstance(strategy_class, type):
                    is_valid = True
                    try:
                        # 排除 StrategyBase 自身
                        if strategy_class is StrategyBase:
                            is_valid = False
                            logger.info(
                                f"Worker {self.worker_id} 策略类 {strategy_class_name} "
                                f"是 StrategyBase 基类本身，自动查找具体子类..."
                            )
                        # 排除 NautilusTrader 的 Strategy 基类
                        elif strategy_class_name == "Strategy":
                            try:
                                from nautilus_trader.trading.strategy import Strategy as NautilusStrategy
                                if strategy_class is NautilusStrategy:
                                    is_valid = False
                                    logger.info(
                                        f"Worker {self.worker_id} 策略类 {strategy_class_name} "
                                        f"是 NautilusTrader Strategy 基类，自动查找具体子类..."
                                    )
                            except ImportError:
                                pass
                        # 排除有未实现抽象方法的子类
                        elif (issubclass(strategy_class, StrategyBase)
                              and getattr(strategy_class, '__abstractmethods__', None)):
                            is_valid = False
                            logger.info(
                                f"Worker {self.worker_id} 策略类 {strategy_class_name} "
                                f"是抽象子类，自动查找具体子类..."
                            )
                    except TypeError:
                        pass
                    
                    if not is_valid:
                        strategy_class = None

            # 如果没有找到或未指定，自动发现策略类
            if strategy_class is None:
                # 导入基类用于类型检查
                from nautilus_trader.trading.strategy import Strategy as NautilusStrategy
                
                logger.info(f"Worker {self.worker_id} 开始自动发现策略类...")
                
                for attr_name in dir(module):
                    # 跳过私有属性和特殊属性
                    if attr_name.startswith('_'):
                        continue
                    
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type):
                        try:
                            # 检查是否是具体策略类（非抽象、非基类）
                            is_strategy_base_subclass = False
                            is_nautilus_strategy_subclass = False
                            
                            # 检查1: QuantCell StrategyBase 的子类
                            try:
                                is_strategy_base_subclass = (
                                    issubclass(attr, StrategyBase)
                                    and attr is not StrategyBase
                                )
                            except TypeError:
                                pass
                            
                            # 检查2: NautilusTrader Strategy 的子类
                            try:
                                is_nautilus_strategy_subclass = (
                                    issubclass(attr, NautilusStrategy)
                                    and attr is not NautilusStrategy
                                )
                            except TypeError:
                                pass
                            
                            # 排除抽象类
                            has_abstract_methods = bool(getattr(attr, '__abstractmethods__', None))
                            
                            # 判断是否为有效的具体策略类
                            is_concrete = (
                                (is_strategy_base_subclass or is_nautilus_strategy_subclass)
                                and not has_abstract_methods
                            )
                            
                            if is_concrete:
                                strategy_class = attr
                                logger.info(
                                    f"Worker {self.worker_id} 自动发现策略类: {attr.__name__}"
                                    f" (类型: {'Nautilus' if is_nautilus_strategy_subclass else 'QuantCell'})"
                                )
                                break
                                
                        except TypeError:
                            pass

                if strategy_class is None:
                    logger.error(
                        f"Worker {self.worker_id} 自动发现策略类失败，"
                        f"模块中的类列表: {[a for a in dir(module) if not a.startswith('_') and isinstance(getattr(module, a), type)]}"
                    )

            if strategy_class is None:
                raise ImportError(f"在 {self.strategy_path} 中未找到策略类")

            # 实例化策略（支持两种初始化模式）
            import inspect

            # 尝试获取策略 __init__ 签名（用于判断初始化模式）
            # 注意：Cython 编译的类（如原生 Nautilus Strategy）可能无法获取签名
            is_nautilus_native = False
            try:
                sig = inspect.signature(strategy_class)
                init_params = list(sig.parameters.keys())

                # 检查是否是 NautilusTrader 原生风格（接收 config 参数）
                if ('config' in init_params or 'strategy_config' in init_params) and strategy_class is not StrategyBase:
                    is_nautilus_native = True
            except (ValueError, TypeError) as e:
                # Cython 编译的类无法获取签名，通过继承关系判断
                logger.debug(f"[_load_trading_strategy] 无法获取 {strategy_class.__name__} 的签名: {e}")
                try:
                    from nautilus_trader.trading.strategy import Strategy as NautilusStrategy
                    if strategy_class is not NautilusStrategy and isinstance(strategy_class, type):
                        try:
                            if issubclass(strategy_class, NautilusStrategy):
                                is_nautilus_native = True
                                logger.info(f"[_load_trading_strategy] 通过继承关系识别为原生 Nautilus 策略")
                        except TypeError:
                            pass
                except ImportError:
                    pass

            # 根据检测结果选择实例化方式
            if is_nautilus_native:
                # === 新增：调用统一的原生策略创建方法 ===
                self.trading_strategy = self._create_nautilus_strategy(strategy_class, module)
            else:
                # 模式 B: 旧版 Dict 参数风格 — 直接 **kwargs 解包
                strategy_params = self.config.get("params", {})
                self.trading_strategy = strategy_class(**strategy_params)

            # 更新状态信息
            self.status.strategy_name = strategy_class.__name__

            logger.info(f"Worker {self.worker_id} 策略加载完成: {strategy_class.__name__}")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 加载策略失败: {e}")
            raise

    async def _handle_start(self):
        """处理启动命令"""
        logger.info(f"Worker {self.worker_id} 收到启动命令，启动 TradingNode")

        try:
            if self.trading_node is None:
                raise RuntimeError("TradingNode 未初始化")

            # 使用 run_async() 启动 TradingNode（在后台任务中运行）
            # 注意：TradingNode 没有 start() 方法，只有 run() 和 run_async()
            # run_async() 是一个长时间运行的协程，会处理所有 Nautilus 事件循环
            logger.info(f"Worker {self.worker_id} 正在创建 Nautilus 运行任务...")
            
            # 创建后台任务运行 TradingNode 的事件循环
            self._nautilus_run_task = asyncio.create_task(
                self._run_nautilus_loop(),
                name=f"nautilus-run-{self.worker_id}"
            )

            # 等待一小段时间让 TradingNode 初始化完成
            await asyncio.sleep(0.5)

            # 检查任务是否还在运行
            if self._nautilus_run_task.done():
                # 如果任务已经结束，说明启动失败
                exc = self._nautilus_run_task.exception()
                if exc:
                    raise RuntimeError(f"Nautilus 启动失败: {exc}")
                else:
                    raise RuntimeError("Nautilus 任务意外退出")

            # 更新状态为 RUNNING
            self.status.update_state(WorkerState.RUNNING)

            # 发送状态更新
            await self._send_status(MessageType.STATUS_UPDATE)

            logger.info(f"Worker {self.worker_id} TradingNode 启动成功（后台运行）")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 启动 TradingNode 失败: {e}")
            self.status.update_state(WorkerState.ERROR)
            self.status.record_error(f"启动失败: {str(e)}")
            await self._send_status(MessageType.ERROR)
            raise

    async def _run_nautilus_loop(self):
        """运行 Nautilus TradingNode 的事件循环
        
        此方法包装了 TradingNode.run_async() 调用，
        在后台任务中持续运行直到被取消。
        
        TradingNode.run_async() 内部会：
        - 启动 kernel
        - 处理数据引擎队列（接收市场数据）
        - 处理执行引擎队列（发送/取消订单）
        - 处理风险引擎队列
        """
        try:
            logger.info(f"Worker {self.worker_id} Nautilus 事件循环开始运行")
            
            # 调用 TradingNode 的 run_async() 方法
            # 这将阻塞在此处，直到：
            # 1. TradingNode 被停止（调用 stop 或 dispose）
            # 2. 发生异常
            # 3. 任务被外部取消
            await self.trading_node.run_async()
            
            logger.info(f"Worker {self.worker_id} Nautilus 事件循环正常退出")
            
        except asyncio.CancelledError:
            logger.info(f"Worker {self.worker_id} Nautilus 循环被取消")
            raise
            
        except Exception as e:
            logger.error(f"Worker {self.worker_id} Nautilus 循环异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.status.update_state(WorkerState.ERROR)
            self.status.record_error(str(e))
            raise

    async def _handle_stop(self):
        """处理停止命令"""
        logger.info(f"Worker {self.worker_id} 收到停止命令，优雅停止 TradingNode")

        try:
            # 更新状态为 STOPPING
            self.status.update_state(WorkerState.STOPPING)
            await self._send_status(MessageType.STATUS_UPDATE)

            # 关键修复：先设置关闭事件标志，让主循环立即退出
            # 这样可以避免主循环在 Nautilus 停止后仍执行健康检查输出失败日志
            logger.info(f"[Stop] Worker {self.worker_id} 设置 _shutdown_event (优先)")
            self._shutdown_event.set()
            logger.info(f"[Stop] Worker {self.worker_id} _shutdown_event 已设置")

            # 1. 停止 Nautilus 运行任务（如果存在）
            if hasattr(self, '_nautilus_run_task') and self._nautilus_run_task:
                logger.info(f"Worker {self.worker_id} 正在停止 Nautilus 运行任务...")
                self._nautilus_run_task.cancel()
                try:
                    await asyncio.wait_for(self._nautilus_run_task, timeout=10.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                self._nautilus_run_task = None
                logger.info(f"Worker {self.worker_id} Nautilus 运行任务已停止")

            # 2. 取消所有未成交订单（可选）
            if self.trading_node:
                try:
                    if hasattr(self.trading_node, 'cancel_all_orders'):
                        await self.trading_node.cancel_all_orders()
                        logger.info(f"Worker {self.worker_id} 已取消所有未成交订单")
                except Exception as e:
                    logger.warning(f"Worker {self.worker_id} 取消订单时出错: {e}")

            # 3. 停止 TradingNode
            if self.trading_node:
                try:
                    if hasattr(self.trading_node, 'dispose'):
                        self.trading_node.dispose()
                        logger.info(f"Worker {self.worker_id} TradingNode 已 dispose")
                    elif hasattr(self.trading_node, 'stop'):
                        stop_result = self.trading_node.stop()
                        if asyncio.iscoroutine(stop_result):
                            await stop_result
                        logger.info(f"Worker {self.worker_id} TradingNode 已 stop")
                    else:
                        logger.warning(f"Worker {self.worker_id} TradingNode 没有 dispose/stop 方法")
                except Exception as e:
                    logger.warning(f"Worker {self.worker_id} 停止 TradingNode 时出错: {e}")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 停止 TradingNode 失败: {e}")
            self.status.record_error(f"停止失败: {str(e)}")
            raise

    async def _cleanup(self):
        """清理资源"""
        logger.info(f"Worker {self.worker_id} 开始清理 TradingNode 资源")

        try:
            # 停止 TradingNode（兼容同步/异步 stop 方法）
            if self.trading_node:
                try:
                    stop_result = self.trading_node.stop()
                    if asyncio.iscoroutine(stop_result):
                        await stop_result
                    logger.info(f"Worker {self.worker_id} TradingNode 已停止")
                except Exception as e:
                    logger.error(f"Worker {self.worker_id} 停止 TradingNode 时出错: {e}")

            # 释放策略资源
            if self.trading_strategy and hasattr(self.trading_strategy, 'on_stop'):
                try:
                    await self._call_strategy_method('on_stop')
                except Exception as e:
                    logger.error(f"Worker {self.worker_id} 策略清理错误: {e}")

            # 释放 NautilusTrader 日志系统的 LogGuard
            if self._nautilus_log_guard:
                try:
                    del self._nautilus_log_guard
                    self._nautilus_log_guard = None
                except Exception as e:
                    logger.warning(f"Worker {self.worker_id} 释放 LogGuard 时出错: {e}")

            # 清理引用
            self.trading_node = None
            self.trading_strategy = None

            logger.info(f"Worker {self.worker_id} TradingNode 资源清理完成")

            # 调用父类清理（统一日志器在父类中最后关闭）
            await super()._cleanup()

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 清理资源时出错: {e}")
            raise

    async def _call_strategy_method(self, method_name: str, *args, **kwargs):
        """安全调用策略方法"""
        if not self.trading_strategy:
            return

        try:
            method = getattr(self.trading_strategy, method_name, None)
            if method is None:
                return

            # 检查是否是协程函数
            if asyncio.iscoroutinefunction(method):
                return await method(*args, **kwargs)
            else:
                return method(*args, **kwargs)

        except Exception as e:
            logger.error(f"策略方法 {method_name} 执行错误: {e}")
            self.status.record_error(f"{method_name}: {str(e)}")
            # 不抛出异常，防止 Worker 崩溃
