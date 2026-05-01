"""
Worker 进程实现

在独立进程中运行策略，通过进程间通信与主进程交互
"""

import multiprocessing
import asyncio
import signal
import os
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from .ipc import WorkerCommClient, Message, MessageType
from .state import WorkerState, WorkerStatus

# 统一文件日志器（替代旧的 ZMQ 日志传输方案）
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
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
    ):
        super().__init__(daemon=True)

        self.worker_id = worker_id
        self.strategy_path = strategy_path
        self.config = config
        self.comm_host = comm_host
        self.data_port = data_port
        self.control_port = control_port
        self.status_port = status_port

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
        self._pause_event = multiprocessing.Event()

        # 统计信息
        self._messages_processed = 0
        self._orders_placed = 0

        # 统一日志器（纯文件存储方案）
        self._unified_logger: Optional[Any] = None

    def run(self):
        """
        进程主入口

        这是进程启动时调用的方法，设置进程环境并启动主循环
        """
        # 设置环境变量，标识这是 Worker 进程
        os.environ['WORKER_ID'] = str(self.worker_id)

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
        except Exception as e:
            logger.error(f"Worker {self.worker_id} 主循环异常: {e}")
            self.status.record_error(str(e))
        finally:
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
                if self._pause_event.is_set():
                    # 暂停状态
                    await asyncio.sleep(0.1)
                    continue

                # 发送心跳
                await self._send_heartbeat()

                # 等待一段时间
                await asyncio.sleep(5)
            
            logger.info(f"[WorkerProcess] Worker {self.worker_id} 主循环退出，_shutdown_event 已设置")

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

        # 初始化日志处理器
        self._init_log_handler()

        self.status.update_state(WorkerState.INITIALIZED)
        logger.info(f"Worker {self.worker_id} 通信连接已建立")

    def _init_log_handler(self):
        """初始化统一文件日志器（替代旧的 ZMQ 日志处理器）"""
        try:
            self._unified_logger = create_unified_logger(
                worker_id=self.worker_id,
            )

            # 安装 stdout 捕获（Tee 模式）
            self._unified_logger.install_stdout_capture()

            # 安装 logging Handler
            self._unified_logger.install_logging_handler()

            # 安装 loguru sink（如果可用）
            self._unified_logger.install_loguru_sink()

            logger.info(
                f"Worker {self.worker_id} 统一文件日志器已初始化 "
                f"(日志文件: {self._unified_logger.get_log_file_path()})"
            )
        except Exception as e:
            logger.error(f"初始化统一日志器失败: {e}")

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
            # 检查是否是 Nautilus 格式的策略（继承自 StrategyBase）
            from strategy.core import StrategyBase
            is_nautilus_strategy = False
            try:
                is_nautilus_strategy = issubclass(strategy_class, StrategyBase)
            except TypeError:
                pass  # strategy_class 不是类

            logger.info(f"[_load_strategy] 策略类 {strategy_class.__name__} 是 Nautilus 策略: {is_nautilus_strategy}")

            if is_nautilus_strategy:
                # Nautilus 格式策略 - 需要创建配置对象
                self.strategy = self._create_nautilus_strategy(strategy_class, module)
            else:
                # 旧格式策略 - 使用字典参数
                strategy_params = self.config.get("params", {})
                self.strategy = strategy_class(strategy_params)

            # 更新状态信息
            self.status.strategy_name = strategy_name or strategy_class.__name__

            # 调用策略初始化
            if hasattr(self.strategy, "on_init"):
                await self._call_strategy_method("on_init")

            logger.info(f"Worker {self.worker_id} 策略加载完成: {strategy_class.__name__}")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 加载策略失败: {e}")
            raise

    def _create_nautilus_strategy(self, strategy_class, module):
        """
        创建 Nautilus 格式的策略实例

        Nautilus 策略需要配置对象作为构造函数参数
        """
        from strategy.core import StrategyConfig, InstrumentId
        from decimal import Decimal

        # 获取配置类
        config_class = None
        config_class_name = strategy_class.__name__ + "Config"
        if hasattr(module, config_class_name):
            config_class = getattr(module, config_class_name)
        else:
            # 使用默认的 StrategyConfig
            config_class = StrategyConfig

        # 从配置中获取交易品种
        symbols = self.config.get("symbols", ["BTCUSDT"])
        exchange = self.config.get("exchange", "binance")
        timeframe = self.config.get("timeframe", "1h")

        # 创建 InstrumentId 列表
        instrument_ids = [
            InstrumentId(symbol, exchange.upper())
            for symbol in symbols
        ]

        # 转换时间周期格式 (e.g., "1h" -> "1-HOUR")
        bar_type = self._convert_timeframe_to_bar_type(timeframe)
        bar_types = [bar_type] * len(instrument_ids)

        # 获取策略参数
        params = self.config.get("params", {})

        # 创建配置对象
        try:
            # 尝试使用策略特定的配置类
            if config_class != StrategyConfig:
                config = config_class(
                    instrument_ids=instrument_ids,
                    bar_types=bar_types,
                    **params
                )
            else:
                # 使用默认配置
                config = StrategyConfig(
                    instrument_ids=instrument_ids,
                    bar_types=bar_types,
                    trade_size=Decimal("0.1"),
                    log_level="INFO"
                )
        except Exception as e:
            logger.warning(f"创建配置对象失败，使用默认配置: {e}")
            config = StrategyConfig(
                instrument_ids=instrument_ids,
                bar_types=bar_types,
                trade_size=Decimal("0.1"),
                log_level="INFO"
            )

        # 创建策略实例
        strategy = strategy_class(config)
        logger.info(f"创建 Nautilus 策略实例: {strategy_class.__name__}，品种: {symbols}")
        return strategy

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
            if data_type == "kline" and hasattr(self.strategy, "on_bar"):
                await self._call_strategy_method("on_bar", data)
            elif data_type == "tick" and hasattr(self.strategy, "on_tick"):
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
            elif message.msg_type == MessageType.PAUSE:
                await self._handle_pause()
            elif message.msg_type == MessageType.RESUME:
                await self._handle_resume()
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

    async def _handle_pause(self):
        """处理暂停命令"""
        logger.info(f"Worker {self.worker_id} 收到暂停命令")
        self._pause_event.set()
        self.status.update_state(WorkerState.PAUSED)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _handle_resume(self):
        """处理恢复命令"""
        logger.info(f"Worker {self.worker_id} 收到恢复命令")
        self._pause_event.clear()
        self.status.update_state(WorkerState.RUNNING)
        await self._send_status(MessageType.STATUS_UPDATE)

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
        if self.strategy and hasattr(self.strategy, "update_params"):
            await self._call_strategy_method("update_params", params)
        await self._send_status(MessageType.STATUS_UPDATE)

    async def _call_strategy_method(self, method_name: str, *args, **kwargs):
        """
        安全调用策略方法

        包装策略方法调用，捕获异常防止策略错误导致 Worker 崩溃
        """
        if not self.strategy:
            return

        try:
            method = getattr(self.strategy, method_name, None)
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

        Args:
            signum: 信号编号
            frame: 当前栈帧
        """
        logger.info(f"Worker {self.worker_id} 收到信号 {signum}")
        self._shutdown_event.set()

    async def _cleanup(self):
        """
        清理资源
        """
        logger.info(f"Worker {self.worker_id} 开始清理资源")

        # 调用策略清理方法
        logger.info(f"[WorkerProcess] Worker {self.worker_id} 开始清理策略...")
        if self.strategy and hasattr(self.strategy, "on_stop"):
            try:
                logger.info(f"[WorkerProcess] Worker {self.worker_id} 调用策略 on_stop...")
                await self._call_strategy_method("on_stop")
                logger.info(f"[WorkerProcess] Worker {self.worker_id} 策略 on_stop 完成")
            except Exception as e:
                logger.error(f"[WorkerProcess] Worker {self.worker_id} 策略清理错误: {e}")
        else:
            logger.info(f"[WorkerProcess] Worker {self.worker_id} 策略无需清理或无 on_stop 方法")

        # 关闭统一文件日志器
        logger.info(f"[WorkerProcess] Worker {self.worker_id} 开始关闭统一日志器...")
        if self._unified_logger:
            try:
                logger.info(f"[WorkerProcess] Worker {self.worker_id} 调用 _unified_logger.close()...")
                self._unified_logger.close()
                logger.info(f"[WorkerProcess] Worker {self.worker_id} 统一日志器已关闭")
            except Exception as e:
                logger.error(f"[WorkerProcess] Worker {self.worker_id} 关闭统一日志器错误: {e}")
        else:
            logger.info(f"[WorkerProcess] Worker {self.worker_id} 无统一日志器需要关闭")

        # 断开通信连接（使用超时避免阻塞）
        logger.info(f"[WorkerProcess] Worker {self.worker_id} 开始断开通信连接...")
        if self.comm_client:
            try:
                # 使用 asyncio.wait_for 设置超时
                import asyncio
                logger.info(f"[WorkerProcess] Worker {self.worker_id} 调用 comm_client.disconnect()...")
                await asyncio.wait_for(self.comm_client.disconnect(), timeout=5.0)
                logger.info(f"[WorkerProcess] Worker {self.worker_id} 通信连接已断开")
            except asyncio.TimeoutError:
                logger.warning(f"[WorkerProcess] Worker {self.worker_id} 断开通信连接超时")
            except Exception as e:
                logger.error(f"[WorkerProcess] Worker {self.worker_id} 断开通信连接错误: {e}")
        else:
            logger.info(f"[WorkerProcess] Worker {self.worker_id} 无通信客户端需要断开")

        # 更新状态
        logger.info(f"[WorkerProcess] Worker {self.worker_id} 更新状态为 STOPPED...")
        self.status.update_state(WorkerState.STOPPED)

        logger.info(f"[WorkerProcess] Worker {self.worker_id} 资源清理完成，进程即将退出")

    def stop(self):
        """
        请求停止 Worker（在主进程中调用）
        """
        self._shutdown_event.set()

    def pause(self):
        """
        请求暂停 Worker（在主进程中调用）
        """
        self._pause_event.set()

    def resume(self):
        """
        请求恢复 Worker（在主进程中调用）
        """
        self._pause_event.clear()

    def is_running(self) -> bool:
        """
        检查 Worker 是否正在运行

        Returns:
            是否正在运行
        """
        return self.is_alive() and not self._shutdown_event.is_set()

    def is_paused(self) -> bool:
        """
        检查 Worker 是否已暂停

        Returns:
            是否已暂停
        """
        return self._pause_event.is_set()


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
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
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

        # Nautilus 统一日志器
        self._nautilus_unified_logger: Optional[Any] = None

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

            # 4. 启动 TradingNode
            await self._handle_start()

            logger.info(f"Worker {self.worker_id} TradingNode 启动完成，开始运行")

            # 5. 主循环 - 等待关闭信号
            check_count = 0
            while not self._shutdown_event.is_set():
                if self._pause_event.is_set():
                    await asyncio.sleep(0.1)
                    continue

                # 每5秒检查一次 Nautilus 状态
                check_count += 1
                if check_count % 5 == 0:
                    is_healthy = await self._check_nautilus_health()
                    if not is_healthy:
                        logger.warning(f"Worker {self.worker_id} Nautilus 健康检查失败")
                        # 可以选择在这里尝试重启或报告错误

                # 发送心跳
                await self._send_heartbeat()

                # 等待一段时间
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 主循环异常: {e}")
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
            log_level = self.trading_config.get("log_level", "INFO")

            # 配置日志目录
            import tempfile
            log_directory = self.trading_config.get("log_directory")
            if not log_directory:
                # 使用临时目录作为默认日志目录
                log_directory = tempfile.gettempdir()
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

            # ========== 关键修复：初始化 NautilusTrader 日志系统 ==========
            # 让 NautilusTrader 的 self.log 输出到 stdout，
            # 这样就能被 UnifiedFileLogger 的 stdout 捕获器捕获
            try:
                from nautilus_trader.common.component import init_logging, LogLevel
                from nautilus_trader.model.identifiers import TraderId

                # 将字符串日志级别转换为 NautilusTrader 的 LogLevel 枚举
                level_map = {
                    "DEBUG": LogLevel.DEBUG,
                    "INFO": LogLevel.INFO,
                    "WARNING": LogLevel.WARNING,
                    "ERROR": LogLevel.ERROR,
                    "CRITICAL": LogLevel.CRITICAL,
                }
                nautilus_log_level = level_map.get(log_level.upper(), LogLevel.DEBUG)

                # 初始化 NautilusTrader 日志系统
                # - level_stdout: 输出到 stdout（被 UnifiedFileLogger 捕获）
                # - level_file: OFF（不写入独立文件，避免重复）
                self._nautilus_log_guard = init_logging(
                    trader_id=TraderId(f"WORKER-{self.worker_id}"),
                    level_stdout=nautilus_log_level,
                    level_file=LogLevel.OFF,
                    bypass=False,
                    colors=False,
                )

                logger.info(
                    f"Worker {self.worker_id} NautilusTrader 日志系统已初始化 "
                    f"(级别: {log_level}, 输出: stdout)"
                )
            except Exception as e:
                logger.warning(
                    f"Worker {self.worker_id} 初始化 NautilusTrader 日志系统失败: {e}"
                )
                # 不影响主流程，继续执行
            # ========== 修复结束 ==========

            # 构建配置
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

            # 构建节点
            trading_node.build()

            # 配置统一文件日志器（替代旧的 ZMQ 日志文件监听器）
            self._setup_nautilus_unified_logger()

            logger.info(f"Worker {self.worker_id} TradingNode 初始化完成")
            return trading_node

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 初始化 TradingNode 失败: {e}")
            self.status.record_error(f"初始化失败: {str(e)}")
            return None

    def _setup_nautilus_unified_logger(self) -> None:
        """
        设置统一文件日志器（用于捕获 NautilusTrader 的 stdout 输出）

        在初始化 NautilusTrader 日志系统后调用，
        确保 UnifiedFileLogger 已安装 stdout 捕获器来接收 NautilusTrader 的日志。
        """
        try:
            # 如果还没有初始化统一日志器，现在初始化
            if self._unified_logger is None:
                self._init_log_handler()

            logger.info(
                f"Worker {self.worker_id} 统一日志器已配置完成 "
                f"(日志文件: {self._unified_logger.get_log_file_path()})"
            )

        except Exception as e:
            logger.warning(f"Worker {self.worker_id} 设置统一日志器失败: {e}")

    def _setup_nautilus_log_file_monitor(self, log_directory: str, log_file_name: str) -> None:
        """
        设置统一文件日志器（替代旧的 ZMQ 日志文件监听器）

        使用纯文件存储方案，捕获所有 Nautilus 日志并写入轮转日志文件。

        Parameters
        ----------
        log_directory : str
            日志目录
        log_file_name : str
            日志文件名
        """
        try:
            # 创建统一文件日志器（专门用于 Nautilus Trader）
            self._nautilus_unified_logger = create_unified_logger(
                worker_id=self.worker_id,
                log_directory=log_directory,
                max_bytes=100 * 1024 * 1024,  # 100MB
                backup_count=10,
            )

            # 安装 stdout 捕获（捕获 Nautilus 的 print 输出）
            self._nautilus_unified_logger.install_stdout_capture()

            # 安装 logging Handler（捕获 logging 模块日志）
            self._nautilus_unified_logger.install_logging_handler()

            # 安装 loguru sink（如果 Nautilus 使用 loguru）
            self._nautilus_unified_logger.install_loguru_sink()

            logger.info(
                f"Worker {self.worker_id} 统一日志器已启动 "
                f"(日志文件: {self._nautilus_unified_logger.get_log_file_path()})"
            )

        except Exception as e:
            logger.warning(f"Worker {self.worker_id} 设置统一日志器失败: {e}")

    async def _load_trading_strategy(self):
        """加载策略"""
        try:
            import importlib.util
            import sys

            # 动态加载策略模块
            module_name = f"trading_strategy_{self.worker_id}"
            spec = importlib.util.spec_from_file_location(
                module_name, self.strategy_path
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载策略文件: {self.strategy_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 获取策略类
            strategy_class_name = self.config.get("strategy_class", "Strategy")
            strategy_class = getattr(module, strategy_class_name, None)
            if strategy_class is None:
                # 尝试查找第一个类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and attr_name not in ["Strategy", "object"]:
                        strategy_class = attr
                        break

            if strategy_class is None:
                raise ImportError(f"在 {self.strategy_path} 中未找到策略类")

            # 实例化策略
            strategy_params = self.config.get("params", {})
            self.trading_strategy = strategy_class(**strategy_params)

            # 将策略添加到 TradingNode
            if self.trading_node:
                self.trading_node.add_strategy(self.trading_strategy)

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

            # 启动 TradingNode
            await self.trading_node.start()

            # 更新状态为 RUNNING
            self.status.update_state(WorkerState.RUNNING)

            # 发送状态更新
            await self._send_status(MessageType.STATUS_UPDATE)

            logger.info(f"Worker {self.worker_id} TradingNode 启动成功")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 启动 TradingNode 失败: {e}")
            self.status.update_state(WorkerState.ERROR)
            self.status.record_error(f"启动失败: {str(e)}")
            await self._send_status(MessageType.ERROR)
            raise

    async def _handle_pause(self):
        """处理暂停命令"""
        logger.info(f"Worker {self.worker_id} 收到暂停命令，暂停策略执行")

        try:
            # 暂停策略执行
            if self.trading_strategy and hasattr(self.trading_strategy, 'pause'):
                await self._call_strategy_method('pause')

            # 停止接收新数据
            self._pause_event.set()

            # 更新状态为 PAUSED
            self.status.update_state(WorkerState.PAUSED)

            # 发送状态更新
            await self._send_status(MessageType.STATUS_UPDATE)

            logger.info(f"Worker {self.worker_id} 策略已暂停")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 暂停策略失败: {e}")
            self.status.record_error(f"暂停失败: {str(e)}")

    async def _handle_resume(self):
        """处理恢复命令"""
        logger.info(f"Worker {self.worker_id} 收到恢复命令，恢复策略执行")

        try:
            # 恢复策略执行
            if self.trading_strategy and hasattr(self.trading_strategy, 'resume'):
                await self._call_strategy_method('resume')

            # 恢复数据接收
            self._pause_event.clear()

            # 更新状态为 RUNNING
            self.status.update_state(WorkerState.RUNNING)

            # 发送状态更新
            await self._send_status(MessageType.STATUS_UPDATE)

            logger.info(f"Worker {self.worker_id} 策略已恢复")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 恢复策略失败: {e}")
            self.status.record_error(f"恢复失败: {str(e)}")

    async def _handle_stop(self):
        """处理停止命令"""
        logger.info(f"Worker {self.worker_id} 收到停止命令，优雅停止 TradingNode")

        try:
            # 更新状态为 STOPPING
            self.status.update_state(WorkerState.STOPPING)
            await self._send_status(MessageType.STATUS_UPDATE)

            # 取消所有未成交订单（可选）
            if self.trading_node and hasattr(self.trading_node, 'cancel_all_orders'):
                try:
                    await self.trading_node.cancel_all_orders()
                    logger.info(f"Worker {self.worker_id} 已取消所有未成交订单")
                except Exception as e:
                    logger.warning(f"Worker {self.worker_id} 取消订单时出错: {e}")

            # 关闭交易所连接
            if self.trading_node:
                await self.trading_node.stop()
                logger.info(f"Worker {self.worker_id} TradingNode 已停止")

            # 设置关闭事件标志
            self._shutdown_event.set()

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 停止 TradingNode 失败: {e}")
            self.status.record_error(f"停止失败: {str(e)}")
            raise

    async def _cleanup(self):
        """清理资源"""
        logger.info(f"Worker {self.worker_id} 开始清理 TradingNode 资源")

        try:
            # 停止 TradingNode
            if self.trading_node:
                try:
                    await self.trading_node.stop()
                    logger.info(f"Worker {self.worker_id} TradingNode 已停止")
                except Exception as e:
                    logger.error(f"Worker {self.worker_id} 停止 TradingNode 时出错: {e}")

            # 释放策略资源
            if self.trading_strategy and hasattr(self.trading_strategy, 'on_stop'):
                try:
                    await self._call_strategy_method('on_stop')
                except Exception as e:
                    logger.error(f"Worker {self.worker_id} 策略清理错误: {e}")

            # 关闭 Nautilus 统一日志器
            try:
                if self._nautilus_unified_logger:
                    self._nautilus_unified_logger.close()
                    logger.info(f"Worker {self.worker_id} Nautilus 统一日志器已关闭")
            except Exception as e:
                logger.warning(f"Worker {self.worker_id} 关闭 Nautilus 统一日志器时出错: {e}")

            # 释放 NautilusTrader 日志系统的 LogGuard
            if self._nautilus_log_guard:
                try:
                    # LogGuard 会在析构时自动清理日志系统
                    del self._nautilus_log_guard
                    self._nautilus_log_guard = None
                    logger.info(f"Worker {self.worker_id} NautilusTrader LogGuard 已释放")
                except Exception as e:
                    logger.warning(f"Worker {self.worker_id} 释放 LogGuard 时出错: {e}")

            # 调用父类清理
            await super()._cleanup()

            # 清理引用
            self.trading_node = None
            self.trading_strategy = None

            logger.info(f"Worker {self.worker_id} TradingNode 资源清理完成")

        except Exception as e:
            logger.error(f"Worker {self.worker_id} 清理资源时出错: {e}")
            raise

    async def _check_nautilus_health(self) -> bool:
        """
        检查 Nautilus 是否正常运行

        Returns:
            bool: Nautilus 是否健康
        """
        if not NAUTILUS_AVAILABLE or self.trading_node is None:
            return False

        try:
            # 检查 TradingNode 是否正在运行
            # 通过检查 kernel 是否存在且正在运行来判断
            if hasattr(self.trading_node, '_kernel'):
                kernel = self.trading_node._kernel
                if kernel is None:
                    logger.debug(f"Worker {self.worker_id} Nautilus kernel 为 None")
                    return False

                # 检查 kernel 是否正在运行
                if hasattr(kernel, 'is_running'):
                    is_running = kernel.is_running()
                    if not is_running:
                        logger.debug(f"Worker {self.worker_id} Nautilus kernel 未在运行")
                    return is_running

                # 如果无法直接检查 is_running，检查是否有 executor
                if hasattr(kernel, '_executor'):
                    executor = kernel._executor
                    if executor is None:
                        logger.debug(f"Worker {self.worker_id} Nautilus executor 为 None")
                        return False

                return True
            else:
                # 如果没有 _kernel 属性，尝试其他方式检查
                # 检查 trading_node 是否有 is_running 方法
                if hasattr(self.trading_node, 'is_running'):
                    return self.trading_node.is_running()

                # 默认认为正在运行（因为 trading_node 存在）
                return True

        except Exception as e:
            logger.debug(f"Worker {self.worker_id} 检查 Nautilus 健康状态失败: {e}")
            return False

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
