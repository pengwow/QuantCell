# -*- coding: utf-8 -*-
"""
事件驱动回测引擎

高性能事件驱动回测引擎实现，支持完整的回测功能。

包含:
    - EventDrivenBacktestEngine: 事件驱动回测引擎类

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-23
"""

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from loguru import logger

try:
    from backend.utils import safe_float
except ImportError:
    from utils import safe_float

from .base import BacktestEngineBase, EngineType


class EventDrivenBacktestEngine(BacktestEngineBase):
    """
    事件驱动回测引擎

    基于事件驱动架构的高性能回测引擎，支持从 CSV/Parquet 加载数据、
    添加交易所、添加交易品种、运行策略等功能。

    Attributes:
        engine_type: 引擎类型标识为 EVENT_DRIVEN
        venues: 已添加的交易所字典
        instruments: 已添加的交易品种字典
        strategies: 已添加的策略列表
        data: 已加载的数据列表
        bar_types: 已定义的 K 线类型字典

    Example:
        >>> config = {
        ...     "trader_id": "BACKTEST-001",
        ...     "log_level": "INFO",
        ...     "initial_capital": 100000.0,
        ...     "start_date": "2023-01-01",
        ...     "end_date": "2023-12-31",
        ... }
        >>> engine = EventDrivenBacktestEngine(config)
        >>> engine.initialize()
        >>> engine.add_venue("SIM", starting_capital=100000.0)
        >>> engine.add_instrument(instrument)
        >>> engine.load_data_from_csv("data.csv", bar_type, instrument)
        >>> engine.add_strategy(strategy)
        >>> results = engine.run_backtest()
        >>> engine.cleanup()
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化事件驱动回测引擎

        Args:
            config: 引擎配置字典，包含:
                - trader_id: 交易者ID（可选，默认 "BACKTEST-001"）
                - log_level: 日志级别（可选，默认 "INFO"）
                - initial_capital: 初始资金（可选，默认 100000.0）
                - start_date: 回测开始日期（可选）
                - end_date: 回测结束日期（可选）
                - cache_database: 缓存数据库配置（可选）
                - streaming: 流式配置（可选）
        """
        super().__init__(config)

        # 核心组件（延迟导入避免启动时加载）
        self._engine: Optional[Any] = None
        self._engine_config: Optional[Any] = None

        # 交易所和品种管理
        self._venues: Dict[str, Any] = {}
        self._instruments: Dict[str, Any] = {}
        self._bar_types: Dict[str, Any] = {}

        # 策略和数据管理
        self._strategies: List[Any] = []
        self._data: List[Any] = []

        # 回测结果缓存
        self._backtest_result: Optional[Any] = None

        logger.debug("事件驱动回测引擎实例已创建")

    @property
    def engine_type(self) -> EngineType:
        """
        引擎类型属性

        Returns:
            EngineType: 返回 EngineType.EVENT_DRIVEN
        """
        return EngineType.EVENT_DRIVEN

    @property
    def engine(self) -> Optional[Any]:
        """
        获取底层引擎实例

        Returns:
            Optional[Any]: 引擎实例，如果未初始化则返回 None
        """
        return self._engine

    def initialize(self) -> None:
        """
        初始化回测引擎

        执行引擎启动前的准备工作，包括:
        - 验证配置有效性
        - 创建引擎配置
        - 初始化核心引擎

        Raises:
            RuntimeError: 初始化失败时抛出
            ValueError: 配置参数无效时抛出
        """
        try:
            logger.info("开始初始化事件驱动回测引擎...")

            # 验证配置
            if not self._validate_config():
                raise ValueError("引擎配置验证失败")

            # 创建引擎配置
            self._setup_engine_config()

            # 延迟导入底层实现
            from nautilus_trader.backtest.engine import BacktestEngine
            self._engine = BacktestEngine(config=self._engine_config)

            self._is_initialized = True
            logger.info("事件驱动回测引擎初始化完成")

        except Exception as e:
            logger.error(f"事件驱动回测引擎初始化失败: {e}")
            raise RuntimeError(f"引擎初始化失败: {e}") from e

    def _setup_engine_config(self) -> None:
        """
        设置引擎配置

        创建引擎配置，配置回测引擎的核心参数，包括:
        - 交易者ID
        - 日志配置
        - 缓存数据库配置（可选）
        - 流式配置（可选）
        """
        # 延迟导入底层实现
        from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
        from nautilus_trader.model import TraderId

        # 获取配置参数
        trader_id_str = self._config.get("trader_id", "BACKTEST-001")
        log_level = self._config.get("log_level", "INFO")

        # 创建引擎配置
        self._engine_config = BacktestEngineConfig(
            trader_id=TraderId(trader_id_str),
            logging=LoggingConfig(log_level=log_level),
        )
        logger.debug(f"引擎配置已创建: trader_id={trader_id_str}, log_level={log_level}")

    def add_venue(
        self,
        venue_name: str,
        oms_type: Any = None,
        account_type: Any = None,
        starting_capital: float = 100000.0,
        base_currency: str = "USD",
        default_leverage: Decimal = Decimal(1),
    ) -> Any:
        """
        添加交易所配置

        向回测引擎添加一个模拟交易所，配置交易环境参数。

        Args:
            venue_name: 交易所名称（如 "SIM", "XCME", "NYSE" 等）
            oms_type: 订单管理系统类型（默认 NETTING）
            account_type: 账户类型（默认 MARGIN）
            starting_capital: 初始资金（默认 100000.0）
            base_currency: 基础货币代码（默认 "USD"）
            default_leverage: 默认杠杆倍数（默认 1，表示无杠杆）

        Returns:
            Any: 创建的交易所标识符

        Raises:
            RuntimeError: 引擎未初始化时抛出
            ValueError: 交易所名称无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not venue_name:
            raise ValueError("交易所名称不能为空")

        try:
            # 延迟导入底层实现
            from nautilus_trader.model import Venue
            from nautilus_trader.model.enums import AccountType, OmsType
            from nautilus_trader.model.objects import Currency, Money

            # 使用默认值
            if oms_type is None:
                oms_type = OmsType.NETTING
            if account_type is None:
                account_type = AccountType.MARGIN

            # 创建交易所标识符
            venue = Venue(venue_name)

            # 创建初始资金
            currency = Currency.from_str(base_currency)
            starting_balances = [Money(starting_capital, currency)]

            # 添加交易所到引擎
            self._engine.add_venue(
                venue=venue,
                oms_type=oms_type,
                account_type=account_type,
                starting_balances=starting_balances,
                base_currency=currency,
                default_leverage=default_leverage,
            )

            # 缓存交易所
            self._venues[venue_name] = venue

            logger.debug(f"交易所已添加: {venue_name}, 初始资金: {starting_capital} {base_currency}")
            return venue

        except Exception as e:
            logger.error(f"添加交易所失败: {e}")
            raise RuntimeError(f"添加交易所失败: {e}") from e

    def add_instrument(self, instrument: Any) -> None:
        """
        添加交易品种

        向回测引擎添加一个交易品种定义。

        Args:
            instrument: 交易品种定义对象

        Raises:
            RuntimeError: 引擎未初始化时抛出
            ValueError: 交易品种无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not instrument:
            raise ValueError("交易品种不能为空")

        try:
            # 添加交易品种到引擎
            self._engine.add_instrument(instrument)

            # 缓存交易品种
            instrument_id_str = str(instrument.id)
            self._instruments[instrument_id_str] = instrument

            logger.debug(f"交易品种已添加: {instrument_id_str}")

        except Exception as e:
            logger.error(f"添加交易品种失败: {e}")
            raise RuntimeError(f"添加交易品种失败: {e}") from e

    def load_data_from_csv(
        self,
        csv_path: Union[str, Path],
        bar_type: Any,
        instrument: Any,
        timestamp_column: str = "timestamp",
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
        columns_mapping: Optional[Dict[str, str]] = None,
        sep: str = ";",
        decimal: str = ".",
    ) -> List[Any]:
        """
        从 CSV 文件加载 K 线数据

        读取 CSV 文件，将数据转换为内部 Bar 对象，并添加到引擎。

        Args:
            csv_path: CSV 文件路径
            bar_type: K 线类型定义
            instrument: 交易品种定义
            timestamp_column: 时间戳列名（默认 "timestamp"）
            timestamp_format: 时间戳格式（默认 "%Y-%m-%d %H:%M:%S"）
            columns_mapping: 列名映射字典
            sep: CSV 分隔符（默认 ";"）
            decimal: 小数点符号（默认 "."）

        Returns:
            List[Any]: 加载的 K 线数据列表

        Raises:
            RuntimeError: 引擎未初始化时抛出
            FileNotFoundError: CSV 文件不存在时抛出
            ValueError: 数据格式无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

        try:
            logger.info(f"开始从 CSV 加载数据: {csv_path}")

            # 延迟导入底层实现
            from nautilus_trader.persistence.wranglers import BarDataWrangler

            # 读取 CSV 文件
            df = pd.read_csv(csv_path, sep=sep, decimal=decimal, header=0, index_col=False)

            # 应用列名映射
            if columns_mapping:
                df = df.rename(columns=columns_mapping)

            # 处理时间戳列
            if timestamp_column in df.columns:
                df[timestamp_column] = pd.to_datetime(df[timestamp_column], format=timestamp_format)
                df = df.rename(columns={timestamp_column: "timestamp"})

            # 设置时间戳为索引
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")

            # 确保必需的列存在
            for col in ["open", "high", "low", "close"]:
                if col not in df.columns:
                    raise ValueError(f"CSV 文件缺少必需的列: {col}")

            # 使用数据处理器转换数据
            wrangler = BarDataWrangler(bar_type, instrument)
            bars: List[Any] = wrangler.process(df)

            # 添加数据到引擎
            self._engine.add_data(bars)
            self._data.extend(bars)

            # 缓存 BarType
            bar_type_str = str(bar_type)
            self._bar_types[bar_type_str] = bar_type

            logger.info(f"CSV 数据加载完成: {len(bars)} 条 K 线")
            return bars

        except Exception as e:
            logger.error(f"从 CSV 加载数据失败: {e}")
            raise RuntimeError(f"从 CSV 加载数据失败: {e}") from e

    def load_data_from_parquet(
        self,
        parquet_path: Union[str, Path],
        bar_type: Any,
        instrument: Any,
        timestamp_column: str = "timestamp",
    ) -> List[Any]:
        """
        从 Parquet 文件加载 K 线数据

        读取 Parquet 文件，将数据转换为内部 Bar 对象，并添加到引擎。

        Args:
            parquet_path: Parquet 文件路径
            bar_type: K 线类型定义
            instrument: 交易品种定义
            timestamp_column: 时间戳列名（默认 "timestamp"）

        Returns:
            List[Any]: 加载的 K 线数据列表

        Raises:
            RuntimeError: 引擎未初始化时抛出
            FileNotFoundError: Parquet 文件不存在时抛出
            ValueError: 数据格式无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        parquet_path = Path(parquet_path)
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet 文件不存在: {parquet_path}")

        try:
            logger.info(f"开始从 Parquet 加载数据: {parquet_path}")

            # 延迟导入底层实现
            from nautilus_trader.persistence.wranglers import BarDataWrangler

            # 读取 Parquet 文件
            df = pd.read_parquet(parquet_path)

            # 处理时间戳列
            if timestamp_column in df.columns:
                df[timestamp_column] = pd.to_datetime(df[timestamp_column])
                df = df.rename(columns={timestamp_column: "timestamp"})

            # 设置时间戳为索引
            if "timestamp" in df.columns:
                df = df.set_index("timestamp")

            # 确保必需的列存在
            for col in ["open", "high", "low", "close"]:
                if col not in df.columns:
                    raise ValueError(f"Parquet 文件缺少必需的列: {col}")

            # 使用数据处理器转换数据
            wrangler = BarDataWrangler(bar_type, instrument)
            bars: List[Any] = wrangler.process(df)

            # 添加数据到引擎
            self._engine.add_data(bars)
            self._data.extend(bars)

            # 缓存 BarType
            bar_type_str = str(bar_type)
            self._bar_types[bar_type_str] = bar_type

            logger.info(f"Parquet 数据加载完成: {len(bars)} 条 K 线")
            return bars

        except Exception as e:
            logger.error(f"从 Parquet 加载数据失败: {e}")
            raise RuntimeError(f"从 Parquet 加载数据失败: {e}") from e

    def add_strategy(self, strategy: Any) -> None:
        """
        添加策略到引擎

        将交易策略添加到回测引擎中。

        Args:
            strategy: 策略实例

        Raises:
            RuntimeError: 引擎未初始化时抛出
            ValueError: 策略无效时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not strategy:
            raise ValueError("策略不能为空")

        try:
            # 检查策略是否有底层实现（EventDrivenStrategy包装器）
            if hasattr(strategy, '_get_strategy_impl'):
                # 使用底层NautilusTrader策略实现
                strategy_impl = strategy._get_strategy_impl()
                self._engine.add_strategy(strategy_impl)
                self._strategies.append(strategy_impl)
                logger.debug(f"策略已添加: {strategy_impl.id}")
            else:
                # 直接使用策略
                self._engine.add_strategy(strategy)
                self._strategies.append(strategy)
                logger.debug(f"策略已添加: {strategy.id}")

        except Exception as e:
            logger.error(f"添加策略失败: {e}")
            raise RuntimeError(f"添加策略失败: {e}") from e

    def run_backtest(self) -> Dict[str, Any]:
        """
        运行回测

        执行完整的回测流程，处理所有历史数据并生成交易记录。

        Returns:
            Dict[str, Any]: 回测结果字典，包含:
                - trades: 交易记录列表
                - equity_curve: 权益曲线
                - metrics: 绩效指标
                - positions: 持仓记录
                - orders: 订单记录
                - account: 账户记录

        Raises:
            RuntimeError: 引擎未初始化或未添加策略时抛出
        """
        if not self._is_initialized or not self._engine:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if not self._strategies:
            raise RuntimeError("未添加策略，请先调用 add_strategy()")

        if not self._data:
            raise RuntimeError("未加载数据，请先调用 load_data_from_csv() 或 load_data_from_parquet()")

        try:
            logger.info("开始执行回测...")

            # 运行回测
            self._engine.run()

            # 处理并返回结果
            results = self._process_results()

            logger.info("回测执行完成")
            return results

        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            raise RuntimeError(f"回测执行失败: {e}") from e

    def _process_results(self) -> Dict[str, Any]:
        """
        处理回测结果

        将底层回测结果转换为内部标准格式。

        Returns:
            Dict[str, Any]: 标准格式的回测结果
        """
        if not self._engine:
            return {}

        try:
            # 获取交易报告
            orders_df = self._engine.trader.generate_order_fills_report()
            positions_df = self._engine.trader.generate_positions_report()

            # 获取账户报告（使用第一个添加的交易所）
            account_df = None
            account_obj = None
            if self._venues:
                first_venue = list(self._venues.values())[0]
                account_df = self._engine.trader.generate_account_report(first_venue)
                # 获取 Account 对象以提取更多信息
                account_obj = self._engine.trader._cache.account_for_venue(first_venue)

            # 调试输出：打印原始数据
            logger.debug(f"订单数据列: {orders_df.columns.tolist() if orders_df is not None else 'None'}")
            logger.debug(f"持仓数据列: {positions_df.columns.tolist() if positions_df is not None else 'None'}")
            logger.debug(f"账户数据列: {account_df.columns.tolist() if account_df is not None else 'None'}")

            # 调试输出：打印前3行数据样本
            if orders_df is not None and not orders_df.empty:
                logger.debug(f"订单数据前3行:\n{orders_df.head(3).to_string()}")
            if positions_df is not None and not positions_df.empty:
                logger.debug(f"持仓数据前3行:\n{positions_df.head(3).to_string()}")
            if account_df is not None and not account_df.empty:
                logger.debug(f"账户数据前3行:\n{account_df.head(3).to_string()}")

            # 转换为标准格式
            trades = self._convert_orders_to_trades(orders_df)
            positions = self._convert_positions(positions_df)

            # 建立 Trade-Position 关联映射
            # 1. 创建 position_id -> position 的映射
            position_map = {pos["position_id"]: pos for pos in positions}

            # 2. 遍历 trades，建立双向关联
            for trade in trades:
                position_id = trade.get("position_id")
                if position_id and position_id in position_map:
                    position = position_map[position_id]
                    # 确保 trade_id 在 position 的 trade_ids 列表中
                    trade_id = trade.get("trade_id")
                    if trade_id and trade_id not in position.get("trade_ids", []):
                        position.setdefault("trade_ids", []).append(trade_id)

            results = {
                "trades": trades,
                "positions": positions,
                "account": self._convert_account(account_df, account_obj),
                "metrics": self._calculate_metrics(positions_df, account_df),
                "equity_curve": self._build_equity_curve(account_df),
            }

            self._results = results
            return results

        except Exception as e:
            logger.error(f"处理回测结果失败: {e}")
            # 输出详细的错误上下文
            import traceback
            logger.error(f"错误堆栈:\n{traceback.format_exc()}")

            # 尝试输出原始数据以便调试
            try:
                if self._engine:
                    orders_df = self._engine.trader.generate_order_fills_report()
                    if orders_df is not None and not orders_df.empty:
                        logger.error(f"订单数据样本:\n{orders_df.head(3).to_string()}")
                        logger.error(f"订单数据类型:\n{orders_df.dtypes.to_string()}")

                    positions_df = self._engine.trader.generate_positions_report()
                    if positions_df is not None and not positions_df.empty:
                        logger.error(f"持仓数据样本:\n{positions_df.head(3).to_string()}")
                        logger.error(f"持仓数据类型:\n{positions_df.dtypes.to_string()}")

                    if self._venues:
                        first_venue = list(self._venues.values())[0]
                        account_df = self._engine.trader.generate_account_report(first_venue)
                        if account_df is not None and not account_df.empty:
                            logger.error(f"账户数据样本:\n{account_df.head(3).to_string()}")
                            logger.error(f"账户数据类型:\n{account_df.dtypes.to_string()}")
            except Exception as debug_e:
                logger.error(f"输出调试信息时出错: {debug_e}")

            return {}

    def _convert_orders_to_trades(self, orders_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        将订单数据转换为交易记录格式

        Args:
            orders_df: 订单 DataFrame

        Returns:
            List[Dict[str, Any]]: 交易记录列表
        """
        if orders_df is None or orders_df.empty:
            return []

        # 打印列名用于调试
        logger.info(f"订单数据列名: {orders_df.columns.tolist()}")
        logger.info(f"订单数据前3行:\n{orders_df.head(3).to_string()}")

        trades = []
        for idx, row in orders_df.iterrows():
            # 尝试多种可能的时间戳列名
            ts = None
            for ts_col in ["timestamp", "ts_init", "ts_event", "created_time", "order_time"]:
                if ts_col in row.index and row.get(ts_col):
                    ts = row.get(ts_col)
                    break
            if ts is None:
                ts = ""

            # 解析时间戳 (NautilusTrader 使用纳秒时间戳)
            formatted_time = ""
            timestamp_val = 0
            from datetime import datetime, timezone

            if isinstance(ts, (int, float)) and ts > 0:
                # 处理纳秒/毫秒时间戳
                # NautilusTrader 使用纳秒时间戳 (19位)
                if ts > 1e18:  # 纳秒时间戳
                    ts_sec = int(ts / 1e9)
                elif ts > 1e12:  # 毫秒时间戳
                    ts_sec = int(ts / 1000)
                else:  # 秒时间戳
                    ts_sec = int(ts)
                dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                timestamp_val = ts_sec
            elif isinstance(ts, str) and ts:
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                    timestamp_val = int(dt.timestamp())
                except:
                    formatted_time = ts
            elif ts and not isinstance(ts, (int, float)) and hasattr(ts, 'strftime') and hasattr(ts, 'timestamp'):
                # pandas Timestamp or datetime object
                formatted_time = ts.strftime('%Y-%m-%d %H:%M:%S')
                timestamp_val = int(ts.timestamp())

            # 尝试多种可能的价格列名
            price = 0.0
            for price_col in ["avg_price", "price", "fill_price", "last_price", "avg_px"]:
                if price_col in row.index:
                    val = row.get(price_col)
                    if val and safe_float(val) > 0:
                        price = safe_float(val)
                        break

            # 尝试多种可能的数量列名
            quantity = 0.0
            for qty_col in ["quantity", "filled_qty", "last_qty", "qty"]:
                if qty_col in row.index:
                    val = row.get(qty_col)
                    if val and safe_float(val) > 0:
                        quantity = safe_float(val)
                        break

            # 确定方向
            side = ""
            for side_col in ["side", "order_side"]:
                if side_col in row.index and row.get(side_col):
                    side = str(row.get(side_col)).upper()
                    break
            direction = "买入" if side == "BUY" else "卖出" if side == "SELL" else side

            # 尝试多种可能的状态列名
            status = "filled"
            for status_col in ["status", "order_status", "state"]:
                if status_col in row.index and row.get(status_col):
                    status = str(row.get(status_col))
                    break

            # 提取 NautilusTrader 原生 ID
            # trade_id: 成交唯一标识
            trade_id = str(row.get("trade_id", row.get("id", idx)))
            # client_order_id: 客户端订单ID
            client_order_id = str(row.get("client_order_id", row.get("order_id", "")))
            # venue_order_id: 交易所订单ID
            venue_order_id = str(row.get("venue_order_id", ""))
            # position_id: 关联的持仓ID
            position_id = str(row.get("position_id", ""))
            # commission: 手续费
            commission = str(row.get("commission", row.get("commissions", "0")))

            trade = {
                "trade_id": trade_id,
                "client_order_id": client_order_id,
                "venue_order_id": venue_order_id,
                "position_id": position_id,
                "instrument_id": str(row.get("instrument_id", row.get("symbol", ""))),
                "side": side,
                "direction": direction,
                "quantity": quantity,
                "price": price,
                "volume": quantity * price,
                "commission": commission,
                "timestamp": timestamp_val,
                "formatted_time": formatted_time,
                "status": status,
            }
            trades.append(trade)

        return trades

    def _convert_positions(self, positions_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        将持仓数据转换为标准格式

        Args:
            positions_df: 持仓 DataFrame

        Returns:
            List[Dict[str, Any]]: 持仓记录列表
        """
        if positions_df is None or positions_df.empty:
            return []

        positions = []
        for idx, row in positions_df.iterrows():
            # 尝试多种可能的position_id列名
            pos_id = ""
            for id_col in ["position_id", "id", "pos_id"]:
                if id_col in row.index and row.get(id_col):
                    pos_id = str(row.get(id_col))
                    break
            if not pos_id:
                pos_id = f"POS_{idx}"

            # 提取 NautilusTrader 原生 ID 和属性
            # opening_order_id: 开仓订单ID
            opening_order_id = str(row.get("opening_order_id", ""))
            # closing_order_id: 平仓订单ID
            closing_order_id = str(row.get("closing_order_id", ""))
            # trade_ids: 关联的所有 trade IDs（逗号分隔的字符串或列表）
            trade_ids_raw = row.get("trade_ids", row.get("fills", ""))
            if isinstance(trade_ids_raw, str) and trade_ids_raw:
                trade_ids = [tid.strip() for tid in trade_ids_raw.split(",") if tid.strip()]
            elif isinstance(trade_ids_raw, list):
                trade_ids = [str(tid) for tid in trade_ids_raw]
            else:
                trade_ids = []

            # 提取时间戳（纳秒）
            ts_opened = row.get("ts_opened", 0)
            ts_closed = row.get("ts_closed", 0)
            duration_ns = row.get("duration_ns", 0)

            # 提取交易量信息
            # quantity: 当前持仓量（平仓后为0）
            current_qty = safe_float(row.get("quantity", row.get("pos_qty", 0)), "quantity")
            # peak_qty: 最大持仓量（实际交易量）
            peak_qty = safe_float(row.get("peak_qty", row.get("max_quantity", current_qty)), "peak_qty")
            # signed_qty: 有符号数量
            signed_qty = safe_float(row.get("signed_qty", row.get("signed_quantity", current_qty)), "signed_qty")

            position = {
                "position_id": pos_id,
                "instrument_id": str(row.get("instrument_id", row.get("symbol", ""))),
                "side": str(row.get("side", row.get("position_side", ""))),
                "quantity": current_qty,  # 当前持仓量（平仓后为0）
                "trade_quantity": peak_qty,  # 实际交易量（使用 peak_qty）
                "signed_quantity": signed_qty,  # 有符号数量
                "avg_px_open": safe_float(row.get("avg_px_open", row.get("avg_price", 0)), "avg_px_open"),
                "avg_px_close": safe_float(row.get("avg_px_close", row.get("close_price", 0)), "avg_px_close"),
                "realized_pnl": str(row.get("realized_pnl", "0")),  # 保留字符串格式
                "opening_order_id": opening_order_id,
                "closing_order_id": closing_order_id,
                "trade_ids": trade_ids,
                "ts_opened": ts_opened,
                "ts_closed": ts_closed,
                "duration_ns": duration_ns,
            }
            positions.append(position)

        return positions

    def _convert_account(self, account_df: Optional[pd.DataFrame], account_obj=None) -> Dict[str, Any]:
        """
        将账户数据转换为标准格式，包含丰富的账户信息

        Args:
            account_df: 账户 DataFrame
            account_obj: NautilusTrader Account 对象（可选）

        Returns:
            Dict[str, Any]: 账户信息字典
        """
        if account_df is None or account_df.empty:
            return {}

        # 从 DataFrame 计算统计数据
        # total 列包含权益曲线数据
        total_series = account_df.get("total", account_df.get("equity", pd.Series()))
        free_series = account_df.get("free", account_df.get("balance", pd.Series()))
        locked_series = account_df.get("locked", account_df.get("margin", pd.Series(dtype=float)))

        # 计算统计数据
        initial_balance = safe_float(total_series.iloc[0]) if len(total_series) > 0 else 0.0
        final_balance = safe_float(total_series.iloc[-1]) if len(total_series) > 0 else 0.0
        max_balance = safe_float(total_series.max()) if len(total_series) > 0 else 0.0
        min_balance = safe_float(total_series.min()) if len(total_series) > 0 else 0.0

        # 获取最后一行作为最终账户状态
        last_row = account_df.iloc[-1]

        # 构建基础账户信息
        account_info = {
            # 基础信息
            "balance": safe_float(free_series.iloc[-1] if len(free_series) > 0 else 0),
            "margin": safe_float(locked_series.iloc[-1] if len(locked_series) > 0 else 0),
            "equity": safe_float(final_balance),

            # 统计数据
            "initial_balance": initial_balance,
            "final_balance": final_balance,
            "max_balance": max_balance,
            "min_balance": min_balance,
            "peak_equity": max_balance,
            "trough_equity": min_balance,
        }

        # 如果提供了 Account 对象，提取更多信息
        if account_obj is not None:
            try:
                # 基础属性
                account_info["id"] = str(account_obj.id) if hasattr(account_obj, 'id') else ""
                account_info["type"] = str(account_obj.type) if hasattr(account_obj, 'type') else ""
                account_info["base_currency"] = str(account_obj.base_currency) if hasattr(account_obj, 'base_currency') and account_obj.base_currency else ""

                # 事件计数
                if hasattr(account_obj, 'event_count'):
                    account_info["event_count"] = account_obj.event_count

                # 起始余额
                if hasattr(account_obj, 'starting_balances'):
                    try:
                        starting_balances = account_obj.starting_balances()
                        if starting_balances:
                            # 获取基础货币的起始余额
                            base_currency = account_obj.base_currency
                            if base_currency and base_currency in starting_balances:
                                account_info["starting_balance"] = float(starting_balances[base_currency])
                            else:
                                # 使用第一个可用货币
                                first_currency = list(starting_balances.keys())[0]
                                account_info["starting_balance"] = float(starting_balances[first_currency])
                    except Exception as e:
                        logger.debug(f"获取起始余额失败: {e}")

                # 手续费
                if hasattr(account_obj, 'commissions'):
                    try:
                        commissions = account_obj.commissions()
                        total_commission = sum(float(money) for money in commissions.values()) if commissions else 0.0
                        account_info["total_commissions"] = total_commission
                    except Exception as e:
                        logger.debug(f"获取手续费失败: {e}")

            except Exception as e:
                logger.warning(f"提取 Account 对象信息失败: {e}")

        return account_info

    def _calculate_metrics(
        self,
        positions_df: Optional[pd.DataFrame],
        account_df: Optional[pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        计算绩效指标

        Args:
            positions_df: 持仓 DataFrame
            account_df: 账户 DataFrame

        Returns:
            Dict[str, Any]: 绩效指标字典
        """
        if positions_df is None or positions_df.empty:
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
            }

        # 提取 PnL 数值
        pnls = []
        for _, row in positions_df.iterrows():
            pnl_raw = row.get("realized_pnl", "0")
            if isinstance(pnl_raw, str):
                # 提取数值部分（移除货币后缀如 USDT, BTC 等）
                # 格式如: "-96.43511300 USDT" -> "-96.43511300"
                import re
                match = re.match(r'^([+-]?\d+\.?\d*)', pnl_raw.strip())
                if match:
                    try:
                        pnl = float(match.group(1))
                    except ValueError:
                        logger.warning(f"无法转换 realized_pnl 数值: {pnl_raw}")
                        pnl = 0.0
                else:
                    pnl = 0.0
            else:
                try:
                    pnl = float(pnl_raw) if pnl_raw is not None else 0.0
                except (ValueError, TypeError):
                    pnl = 0.0
            pnls.append(pnl)

        pnls = [p for p in pnls if p != 0]

        if not pnls:
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
            }

        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]

        total_pnl = sum(pnls)
        win_rate = len(winning_trades) / len(pnls) * 100 if pnls else 0

        profit_factor = 0.0
        if losing_trades:
            gross_profit = sum(winning_trades) if winning_trades else 0
            gross_loss = abs(sum(losing_trades))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # 计算总收益率
        initial_capital = self._config.get("initial_capital", 100000.0)
        total_return = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0

        # 计算夏普比率 (使用权益曲线数据)
        sharpe_ratio = 0.0
        max_drawdown = 0.0
        if account_df is not None and not account_df.empty:
            # 构建权益曲线
            equity_curve = self._build_equity_curve(account_df)
            if equity_curve:
                equities = [point.get("equity", 0) for point in equity_curve]
                
                # 计算收益率序列
                if len(equities) > 1:
                    returns = []
                    for i in range(1, len(equities)):
                        if equities[i-1] > 0:
                            ret = (equities[i] - equities[i-1]) / equities[i-1]
                            returns.append(ret)
                    
                    # 计算夏普比率
                    if len(returns) > 1:
                        import numpy as np
                        avg_return = np.mean(returns)
                        std_return = np.std(returns, ddof=1)
                        # 假设无风险利率为0，年化因子假设每小时数据，每年252个交易日，每天24小时
                        periods_per_year = 252 * 24
                        if std_return > 0:
                            sharpe_ratio = (avg_return / std_return) * np.sqrt(periods_per_year)
                    
                    # 计算最大回撤
                    peak = equities[0]
                    for equity in equities:
                        if equity > peak:
                            peak = equity
                        drawdown = (peak - equity) / peak if peak > 0 else 0
                        if drawdown > max_drawdown:
                            max_drawdown = drawdown
                    max_drawdown = max_drawdown * 100  # 转换为百分比

        return {
            "total_return": round(total_return, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown": round(max_drawdown, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_trades": len(pnls),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "total_pnl": round(total_pnl, 2),
        }

    def _build_equity_curve(self, account_df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        构建权益曲线

        Args:
            account_df: 账户 DataFrame

        Returns:
            List[Dict[str, Any]]: 权益曲线数据点列表
        """
        if account_df is None or account_df.empty:
            return []

        equity_curve = []
        for _, row in account_df.iterrows():
            # NautilusTrader 使用 total/free/locked 列名
            # total = free + locked (locked 是保证金占用)

            # 处理时间戳 - 从DataFrame索引或timestamp列获取
            ts = None
            # 首先尝试从timestamp列获取
            if "timestamp" in account_df.columns:
                ts = row.get("timestamp")
            # 如果为空，使用DataFrame索引
            if ts is None or (isinstance(ts, float) and pd.isna(ts)):
                ts = row.name  # DataFrame索引

            # 处理时间戳 - 统一转换为秒级Unix时间戳和格式化字符串
            ts_numeric = 0  # 数值型Unix时间戳（秒）
            ts_str = ""     # 格式化时间字符串
            
            if isinstance(ts, (int, float)) and ts > 0:
                from datetime import datetime, timezone
                # 根据时间戳位数判断精度并统一转换为秒
                if ts > 1e18:  # 纳秒时间戳 (19位+)
                    ts_numeric = int(ts / 1e9)
                elif ts > 1e15:  # 微秒时间戳 (16-18位)
                    ts_numeric = int(ts / 1e6)
                elif ts > 1e12:  # 毫秒时间戳 (13-15位)
                    ts_numeric = int(ts / 1e3)
                else:  # 秒时间戳 (10-12位)
                    ts_numeric = int(ts)
                
                dt = datetime.fromtimestamp(ts_numeric, tz=timezone.utc)
                ts_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(ts, str):
                # 字符串时间戳，尝试解析
                ts_str = ts
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    ts_numeric = int(dt.timestamp())
                except:
                    # 如果解析失败，保持原样
                    ts_numeric = 0
            elif hasattr(ts, 'timestamp') and callable(getattr(ts, 'timestamp', None)):
                # pandas Timestamp or datetime object
                try:
                    ts_numeric = int(ts.timestamp())
                    ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    ts_str = str(ts)
                    ts_numeric = 0

            point = {
                "timestamp": ts_numeric,  # Unix时间戳（秒，数值型）
                "formatted_time": ts_str,  # 格式化时间字符串
                "equity": safe_float(row.get("total", row.get("equity", 0))),
                "balance": safe_float(row.get("free", row.get("balance", 0))),
                "margin": safe_float(row.get("locked", row.get("margin", 0))),
            }
            equity_curve.append(point)

        return equity_curve

    def get_results(self) -> Dict[str, Any]:
        """
        获取回测结果

        返回最近一次回测的完整结果。

        Returns:
            Dict[str, Any]: 回测结果字典

        Raises:
            RuntimeError: 尚未执行回测时抛出
        """
        if not self._results:
            raise RuntimeError("尚未执行回测，请先调用 run_backtest()")

        return self._results

    def cleanup(self) -> None:
        """
        清理资源

        释放引擎占用的所有资源，包括:
        - 释放底层引擎资源
        - 关闭数据连接
        - 释放内存缓存
        - 重置内部状态

        此方法应在回测完成后调用，确保资源正确释放。
        """
        logger.info("开始清理回测引擎资源...")

        # 释放底层引擎资源
        if self._engine:
            try:
                self._engine.dispose()
                logger.debug("底层引擎已释放")
            except Exception as e:
                logger.warning(f"释放引擎时出错: {e}")

        # 重置所有状态
        self._engine = None
        self._engine_config = None
        self._venues.clear()
        self._instruments.clear()
        self._bar_types.clear()
        self._strategies.clear()
        self._data.clear()
        self._backtest_result = None

        # 调用基类的状态重置
        self._reset_state()

        logger.info("回测引擎资源清理完成")

    def get_venue(self, venue_name: str) -> Optional[Any]:
        """
        获取已添加的交易所

        Args:
            venue_name: 交易所名称

        Returns:
            Optional[Any]: 交易所标识符，如果不存在则返回 None
        """
        return self._venues.get(venue_name)

    def get_instrument(self, instrument_id: str) -> Optional[Any]:
        """
        获取已添加的交易品种

        Args:
            instrument_id: 交易品种ID

        Returns:
            Optional[Any]: 交易品种定义，如果不存在则返回 None
        """
        return self._instruments.get(instrument_id)

    def get_bar_type(self, bar_type_str: str) -> Optional[Any]:
        """
        获取已定义的 K 线类型

        Args:
            bar_type_str: K 线类型字符串表示

        Returns:
            Optional[Any]: K 线类型对象，如果不存在则返回 None
        """
        return self._bar_types.get(bar_type_str)

    def get_strategies(self) -> List[Any]:
        """
        获取已添加的策略列表

        Returns:
            List[Any]: 策略列表
        """
        return self._strategies.copy()

    def get_data_count(self) -> int:
        """
        获取已加载的数据条数

        Returns:
            int: 数据条数
        """
        return len(self._data)
